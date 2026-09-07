"""Independent stateful queue evaluation; expected answers stay outside the sandbox."""

import argparse
import fcntl
import json
from pathlib import Path
import sys
import tempfile

from evaluate_fixture import bounded_json, candidate_files
from evaluate_fixture import observe as public_observe
from queue_cases import CASES, CLI_INVALID, ERROR, job
from queue_fixture import FIXTURE, evaluator_fingerprint
from queue_sandbox import observe
from setup_fixture import git, sha256
from terminal_run import capture_diff, observe_terminal


def equal(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def evaluate(repository, sandbox, output, fixture_manifest, run=None):
    repository, sandbox, output = (
        repository.resolve(),
        sandbox.absolute(),
        output.resolve(),
    )
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        raise ValueError("queue evaluation requires Linux/Python 3.12")
    if (
        sandbox.name != "codex-linux-sandbox"
        or output.is_relative_to(repository)
        or repository.is_relative_to(output)
    ):
        raise ValueError("invalid sandbox alias or output location")
    directory = Path(git(repository, "rev-parse", "--absolute-git-dir"))
    lock_path = directory / "codex-lab-launch.lock"
    if lock_path.is_symlink():
        raise ValueError("linked launch lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return evaluate_locked(repository, sandbox, output, fixture_manifest, run)


def evaluate_locked(repository, sandbox, output, fixture_manifest, run):
    metadata = bounded_json(fixture_manifest)
    fingerprint = evaluator_fingerprint()
    if (
        metadata["fixture"] != "durable-queue-v1"
        or Path(metadata["repository"]).resolve() != repository
        or git(repository, "rev-parse", "HEAD") != metadata["commit"]
        or metadata["python"]["sha256"] != sha256(Path(sys.executable).resolve())
        or metadata["task_sha256"] != sha256(FIXTURE / "task.txt")
        or metadata["evaluator_sha256"] != fingerprint
    ):
        raise ValueError("fixture baseline, interpreter, task or evaluator changed")
    snapshot, observation = None, None
    if run is not None:
        snapshot, spec, observation = observe_terminal(run)
        if (
            observation["repository"] != str(repository)
            or spec["repository"]["commit"] != metadata["commit"]
            or spec["task"].encode() != (FIXTURE / "task.txt").read_bytes()
        ):
            raise ValueError("run does not match frozen queue task")
    before = candidate_files(repository)
    patch, git_metadata = capture_diff(repository, metadata["commit"])
    output.mkdir(exist_ok=False)
    checks = []
    with tempfile.TemporaryDirectory(prefix="queue-evaluation-") as temporary:
        base = Path(temporary)
        probe = observe(
            sandbox,
            repository,
            base,
            "probe",
            {"private": str(fixture_manifest.resolve())},
        )
        if probe["exit_code"] != 0 or probe["value"] != "isolated":
            raise ValueError(
                "queue evaluator sandbox probe failed: " + probe["stderr"][:4096]
            )
        for index, case in enumerate(CASES):
            for mode in ("api", "cli"):
                scratch = base / f"{index}-{mode}"
                scratch.mkdir()
                result = observe(
                    sandbox, repository, scratch, mode, {"steps": case["steps"]}
                )
                checks.append(
                    {
                        "case": case["name"],
                        "mode": mode,
                        "passed": result["exit_code"] == 0
                        and equal(result["value"], case["expected"]),
                        "observation": result,
                    }
                )
        invalid_requests = [{"bytes": list(value)} for value in CLI_INVALID]
        invalid_requests += [
            {"bytes": list(b'{"op":"list"}'), "variant": variant}
            for variant in ("missing_file", "usage", "extra", "database")
        ]
        for index, request in enumerate(invalid_requests):
            scratch = base / f"invalid-{index}"
            scratch.mkdir()
            result = observe(sandbox, repository, scratch, "cli_invalid", request)
            checks.append(
                {
                    "case": f"invalid-request-{index}",
                    "mode": "cli_invalid",
                    "passed": result["exit_code"] == 0
                    and equal(
                        result["value"], {"result": ERROR, "preserved": job("keep")}
                    ),
                    "observation": result,
                }
            )
        for count in (1, 2):
            for repeat in range(3):
                scratch = base / f"race-{count}-{repeat}"
                scratch.mkdir()
                result = observe(sandbox, repository, scratch, "race", {"jobs": count})
                expected = {
                    "claims": [chr(97 + i) for i in range(count)],
                    "unique": True,
                    "processes": 2,
                    "errors": [],
                    "exits": [0, 0],
                    "attempts": {chr(97 + i): 1 for i in range(count)},
                }
                checks.append(
                    {
                        "case": f"atomic-claim-{count}-{repeat}",
                        "mode": "race",
                        "passed": result["exit_code"] == 0
                        and equal(result["value"], expected),
                        "observation": result,
                    }
                )
        public = public_observe(
            sandbox, repository, base, "public", argument=FIXTURE / "project/tests"
        )
    final_patch, final_git = capture_diff(repository, metadata["commit"])
    if (
        candidate_files(repository) != before
        or final_patch != patch
        or final_git != git_metadata
    ):
        raise ValueError("candidate changed during evaluation")
    if snapshot is not None:
        snapshot.verify_unchanged()
        current, _, _ = observe_terminal(run)
        if current.hashes != snapshot.hashes:
            raise ValueError("run inventory changed during evaluation")
        observation["git"] = git_metadata
        (output / "observation.json").write_text(
            json.dumps(observation, indent=2) + "\n"
        )
    result = {
        "schema_version": 1,
        "fixture": metadata["fixture"],
        "fixture_commit": metadata["commit"],
        "task_sha256": metadata["task_sha256"],
        "evaluator_sha256": fingerprint,
        "sandbox_sha256": sha256(sandbox.resolve()),
        "python": metadata["python"],
        "run": str(run) if run else None,
        "candidate_files": before,
        "public_test_success": public["exit_code"] == 0,
        "hidden_test_success": all(c["passed"] for c in checks),
        "public": public,
        "checks": checks,
        "git": git_metadata,
    }
    result["task_success"] = (
        result["public_test_success"] and result["hidden_test_success"]
    )
    (output / "candidate.diff").write_bytes(patch)
    (output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository", "sandbox", "output", "fixture-manifest", "run"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        args.repository, args.sandbox, args.output, args.fixture_manifest, args.run
    )
    print(
        json.dumps(
            {
                "task_success": result["task_success"],
                "passed": sum(c["passed"] for c in result["checks"]),
                "total": len(result["checks"]),
            }
        )
    )
