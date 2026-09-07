"""Observe fixed public/hidden cases through the existing Codex Linux sandbox."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

from fixture_cases import CASES
from setup_fixture import FIXTURE, evaluator_fingerprint, git, sha256

WORKER = Path(__file__).resolve().with_name("evaluation_worker.py")
MAX_OUTPUT = 1024 * 1024


def candidate_files(repository: Path) -> dict:
    files = sorted(path for path in repository.rglob("*.py") if ".git" not in path.parts)
    if len(files) > 128:
        raise ValueError("candidate exceeds file inventory limit")
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(repository) or path.stat().st_size > MAX_OUTPUT:
            raise ValueError("candidate file is escaping, linked or oversized")
    return {str(path.relative_to(repository)): sha256(path) for path in files}


def bounded_json(path: Path) -> dict:
    with path.open("rb") as source:
        data = source.read(MAX_OUTPUT + 1)
    if len(data) > MAX_OUTPUT:
        raise ValueError("metadata exceeds byte limit")
    return json.loads(data)


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def observe(binary: Path, repository: Path, scratch: Path, mode: str,
            payload: bytes = b"", argument: Path | None = None) -> dict:
    python = Path(sys.executable).resolve()
    # Allow only interpreter/runtime files, the candidate, and specific trusted
    # observation inputs. Expected answers, homes and credentials are absent.
    reads = [Path(sys.base_prefix), binary, binary.resolve(),
             binary.resolve().parent / "codex-resources", WORKER, repository]
    if mode == "public":
        reads.append(FIXTURE / "project/tests")
    entries = [{"path": {"type": "path", "path": str(path)}, "access": "read"}
               for path in reads if path.exists()]
    # Upstream's minimal system view preserves logical dynamic-loader aliases
    # such as /lib64 on merged-/usr systems, without mounting user homes.
    entries.append({"path": {"type": "special", "value": {"kind": "minimal"}}, "access": "read"})
    entries.append({"path": {"type": "path", "path": str(scratch)}, "access": "write"})
    profile = {"type": "managed", "network": "restricted",
               "file_system": {"type": "restricted", "entries": entries}}
    command = [str(binary), "--sandbox-policy-cwd", str(repository),
               "--permission-profile", json.dumps(profile), "--", str(python), "-I", "-B",
               str(WORKER), str(repository), mode]
    if argument is not None:
        command.append(str(argument))
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                   "HOME": str(scratch), "TMPDIR": str(scratch)}
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            result = subprocess.run(command, executable=str(binary), env=environment,
                                    cwd=repository, input=payload, stdout=stdout, stderr=stderr,
                                    timeout=20, check=False, preexec_fn=limits)
            exit_code = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code, timed_out = None, True
        stdout.seek(0)
        stderr.seek(0)
        output = stdout.read(MAX_OUTPUT + 1)
        diagnostic = stderr.read(MAX_OUTPUT + 1)
    return {"exit_code": exit_code, "timeout": timed_out,
            "stdout": output.decode("utf-8", errors="replace"),
            "stderr": diagnostic.decode("utf-8", errors="replace"),
            "wall_clock_ms": round((time.monotonic() - started) * 1000)}


def evaluate(repository: Path, sandbox: Path, output: Path, fixture_manifest: Path,
             run: Path | None = None) -> dict:
    directory = Path(git(repository, "rev-parse", "--absolute-git-dir"))
    lock_path = directory / "codex-lab-launch.lock"
    if lock_path.is_symlink():
        raise ValueError("invalid launch lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return evaluate_locked(repository, sandbox, output, fixture_manifest, run)


def evaluate_locked(repository: Path, sandbox: Path, output: Path, fixture_manifest: Path,
                    run: Path | None) -> dict:
    if sys.version_info[:2] != (3, 12) or sys.platform != "linux":
        raise ValueError("evaluation requires Linux and Python 3.12")
    repository, sandbox, output = repository.resolve(), sandbox.absolute(), output.resolve()
    if output.is_relative_to(repository) or repository.is_relative_to(output):
        raise ValueError("evaluation output must be separate from the candidate")
    if sandbox.name != "codex-linux-sandbox":
        raise ValueError("use the existing codex-linux-sandbox dispatch alias")
    metadata = bounded_json(fixture_manifest)
    if git(repository, "rev-parse", "HEAD") != metadata["commit"]:
        raise ValueError("candidate commit differs from fixture baseline")
    if metadata["python"]["sha256"] != sha256(Path(sys.executable).resolve()):
        raise ValueError("fixture Python changed")
    if metadata["evaluator_sha256"] != evaluator_fingerprint():
        raise ValueError("evaluator changed after fixture setup")
    if run is not None:
        with (run / "events.jsonl").open("rb") as source:
            events = source.read(MAX_OUTPUT + 1)
        if len(events) > MAX_OUTPUT or not events.endswith(b"\n"):
            raise ValueError("invalid run journal")
        if json.loads(events.splitlines()[-1])["state"] != "completed":
            raise ValueError("evaluate only after the model workflow completes and shuts down")
        spec = bounded_json(run / "config/run-spec.json")
        if spec["repository"]["commit"] != metadata["commit"] or spec["task"].encode() != (FIXTURE / "task.txt").read_bytes():
            raise ValueError("run does not match fixture task and baseline")
    before = candidate_files(repository)
    output.mkdir(parents=False, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="codex-lab-evaluator-") as temporary:
        scratch = Path(temporary)
        probe = observe(sandbox, repository, scratch, "probe", argument=fixture_manifest.resolve())
        if probe["exit_code"] != 0 or probe["stdout"] != "isolated\n":
            raise ValueError("evaluator sandbox probe failed: " + probe["stderr"][:4096])
        api = observe(sandbox, repository, scratch, "api", json.dumps([case[1] for case in CASES]).encode())
        try:
            values = json.loads(api["stdout"]) if api["exit_code"] == 0 else []
        except ValueError:
            values = []
        checks = []
        for index, (name, text, expected) in enumerate(CASES):
            wanted = {"error": "ValueError"} if expected is None else {"value": expected}
            api_passed = (isinstance(values, list) and len(values) == len(CASES)
                          and json.dumps(values[index], sort_keys=True) == json.dumps(wanted, sort_keys=True))
            source = scratch / "input.csv"
            source.write_bytes(text.encode("utf-8"))
            cli = observe(sandbox, repository, scratch, "cli", argument=source)
            expected_stdout = "" if expected is None else json.dumps(expected, sort_keys=True) + "\n"
            cli_passed = cli["exit_code"] == (2 if expected is None else 0) and cli["stdout"] == expected_stdout
            checks.append({"case": name, "api_passed": api_passed, "cli_passed": cli_passed, "cli": cli})
        public = observe(sandbox, repository, scratch, "public", argument=FIXTURE / "project/tests")
    result = {"schema_version": 1, "fixture": metadata["fixture"], "fixture_commit": metadata["commit"],
              "task_sha256": metadata["task_sha256"], "python": metadata["python"],
              "evaluator_sha256": evaluator_fingerprint(), "sandbox_sha256": sha256(sandbox.resolve()),
              "run": str(run.resolve()) if run else None,
              "candidate_files": candidate_files(repository),
              "public_test_success": public["exit_code"] == 0,
              "hidden_test_success": all(check["api_passed"] and check["cli_passed"] for check in checks),
              "api": api, "public": public, "checks": checks}
    if result["candidate_files"] != before:
        raise ValueError("candidate changed during evaluation")
    result["task_success"] = result["public_test_success"] and result["hidden_test_success"]
    (output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ["repository", "sandbox", "output", "fixture-manifest"]:
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.repository, args.sandbox, args.output, args.fixture_manifest, args.run)
    print(json.dumps({key: result[key] for key in ["task_success", "public_test_success", "hidden_test_success"]}))
