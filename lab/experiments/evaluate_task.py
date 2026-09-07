"""Independently grade a stopped repository task without exposing expected answers."""

import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sys
import tempfile

from setup_fixture import git, sha256
from task_registry import evaluator_fingerprint, inventory, load_task, read_json, relative_path, task_text
from task_sandbox import observe
from terminal_run import capture_diff, observe_terminal


def render(arguments, repository, scratch, toolchain):
    values = {"python": str(Path(sys.executable).resolve()),
              "repository": str(repository), "scratch": str(scratch)}
    if toolchain:
        values.update(cargo=str(Path(toolchain) / "bin/cargo"),
                      rustc=str(Path(toolchain) / "bin/rustc"))
    result = []
    for argument in arguments:
        for name, value in values.items():
            argument = argument.replace("{" + name + "}", value)
        if any("{" + name + "}" in argument for name in ("cargo", "rustc")):
            raise ValueError("Rust command requires a pinned task toolchain")
        result.append(argument)
    return result


def scope_changes(before, after, writes):
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    return sorted(name for name in changed
                  if not any(name == root or name.startswith(root + "/") for root in writes))


def matches(result, expected, scratch):
    if (result["timeout"] or result["output_truncated"] or result.get("invalid_utf8")
            or result["exit_code"] != expected["exit"]):
        return False
    if "stdout" in expected and result["stdout"] != expected["stdout"]:
        return False
    if "stdout_json" in expected:
        try:
            value = json.loads(result["stdout"])
        except (ValueError, TypeError):
            return False
        if json.dumps(value, sort_keys=True) != json.dumps(expected["stdout_json"], sort_keys=True):
            return False
    if expected.get("stderr_contains", "") not in result["stderr"]:
        return False
    if any(token not in result["stderr"] for token in expected.get("stderr_contains_all", [])):
        return False
    for name, content in expected.get("files", {}).items():
        try:
            path = relative_path(scratch, name)
            if content is None:
                if path.exists():
                    return False
            elif (not path.is_file() or path.stat().st_size > 2 * 1024 * 1024
                  or path.read_bytes() != content.encode("utf-8")):
                return False
        except (ValueError, OSError, UnicodeError):
            return False
    return True


def check_cases(cases):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 256:
        raise ValueError("task must declare 1..256 private cases")
    ids = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or case["id"] in ids:
            raise ValueError("invalid or duplicate case ID")
        ids.add(case["id"])
        if not 1 <= len(case["steps"]) <= 32:
            raise ValueError("private case step limit exceeded")
        for name, value in case.get("files", {}).items():
            relative_path(Path("/unused"), name)
            if not isinstance(value, str):
                raise ValueError("case input files must contain text")
        for step in case["steps"]:
            if (not isinstance(step.get("stdin", ""), str)
                    or not isinstance(step.get("argv", []), list)
                    or len(step.get("argv", [])) > 32
                    or any(not isinstance(arg, str) or "\0" in arg for arg in step.get("argv", []))
                    or type(step["expect"].get("exit")) is not int):
                raise ValueError("invalid case invocation or expected exit status")
            expected = step["expect"]
            if (set(expected) - {"exit", "stdout", "stdout_json", "stderr_contains", "stderr_contains_all", "files"}
                    or any(not isinstance(expected[key], str) for key in ("stdout", "stderr_contains") if key in expected)
                    or not isinstance(expected.get("stderr_contains_all", []), list)
                    or any(not isinstance(token, str) or not token for token in expected.get("stderr_contains_all", []))
                    or not isinstance(expected.get("files", {}), dict)):
                raise ValueError("invalid private expectation")
            for name, content in expected.get("files", {}).items():
                relative_path(Path("/unused"), name)
                if content is not None and not isinstance(content, str):
                    raise ValueError("expected files must contain text or be absent")


def grade(repository, sandbox, task, toolchain=None):
    cases = read_json(task.root / "private/cases.json")
    check_cases(cases)
    checks = []
    with tempfile.TemporaryDirectory(prefix="codex-task-grade-") as temporary:
        base = Path(temporary)
        candidate, scratch = base / "candidate", base / "scratch"
        # Build an observed copy with frozen public tests. Candidate-written tests
        # cannot replace the independent public baseline or private expectations.
        shutil.copytree(repository, candidate, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        public_tests = candidate / "tests"
        if public_tests.exists():
            if public_tests.is_dir():
                shutil.rmtree(public_tests)
            else:
                public_tests.unlink()
        shutil.copytree(task.root / "project/tests", public_tests)
        scratch.mkdir()
        candidate_before = inventory(candidate)
        probe = observe(sandbox, candidate, scratch,
                        [str(Path(sys.executable).resolve()), "-I", "-B", "-c",
                         "import os,sys; assert not os.access(sys.argv[1],os.R_OK); "
                         "assert not os.access(sys.argv[2],os.W_OK); "
                         "open(sys.argv[3],'w').write('ok')",
                         str(task.root / "private/cases.json"), str(candidate / "TASK.md"),
                         str(scratch / "probe")], toolchain=toolchain)
        if probe["exit_code"] != 0 or probe["timeout"]:
            raise ValueError("task evaluator sandbox probe failed: " + probe["stderr"][:2048])
        public_scratch = base / "public-scratch"
        public_scratch.mkdir()
        public = observe(sandbox, candidate, public_scratch,
                         render(task.manifest["public_command"], candidate, public_scratch, toolchain),
                         toolchain=toolchain)
        build = None
        if task.manifest["build"]:
            build = observe(sandbox, candidate, scratch,
                            render(task.manifest["build"], candidate, scratch, toolchain),
                            toolchain=toolchain)
        build_ok = build is None or (build["exit_code"] == 0 and not build["timeout"] and not build["output_truncated"])
        if build_ok:
            command = render(task.manifest["command"], candidate, scratch, toolchain)
            for index, case in enumerate(cases):
                directory = base / f"case-{index}"
                directory.mkdir()
                for name, content in case.get("files", {}).items():
                    path = relative_path(directory, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content.encode("utf-8"))
                for step_index, step in enumerate(case["steps"]):
                    result = observe(sandbox, candidate, scratch, [*command, *step.get("argv", [])],
                                     cwd=directory, stdin=step.get("stdin", ""), toolchain=toolchain,
                                     write_root=directory)
                    checks.append({"case": case["id"], "step": step_index,
                                   "passed": matches(result, step["expect"], directory),
                                   "observation": result})
        if inventory(candidate) != candidate_before:
            raise ValueError("read-only grading copy changed")
    public_ok = public["exit_code"] == 0 and not public["timeout"] and not public["output_truncated"]
    private_ok = build_ok and bool(checks) and all(check["passed"] for check in checks)
    return {"build": build, "build_success": build_ok, "public": public,
            "public_test_success": public_ok, "hidden_test_success": private_ok,
            "checks": checks, "task_success": public_ok and private_ok}


def evaluate(repository, sandbox, output, fixture_manifest, run=None, toolchain=None):
    repository, output = Path(repository).resolve(), Path(output).resolve()
    if output.is_relative_to(repository) or repository.is_relative_to(output):
        raise ValueError("grading output must not overlap candidate")
    metadata = read_json(fixture_manifest)
    task = load_task(metadata["task_root"])
    if metadata.get("task_toolchain") != (str(toolchain) if toolchain is not None else None):
        raise ValueError("task toolchain differs from prepared task")
    if (metadata["kind"] != "repository_task" or metadata["fixture"] != task.name
            or Path(metadata["repository"]).resolve() != repository
            or git(repository, "rev-parse", "HEAD") != metadata["commit"]
            or metadata["assets"] != inventory(task.root)
            or metadata["evaluator"] != evaluator_fingerprint()
            or metadata["python_sha256"] != sha256(Path(sys.executable).resolve())):
        raise ValueError("task baseline, interpreter, assets or evaluator changed")
    directory = Path(git(repository, "rev-parse", "--absolute-git-dir"))
    lock_path = directory / "codex-lab-launch.lock"
    if lock_path.is_symlink():
        raise ValueError("linked task launch lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        snapshot, observation = None, None
        if run is not None:
            snapshot, spec, observation = observe_terminal(Path(run))
            if (not observation.get("task_scope_sha256")
                    or snapshot.json("evidence/task-scope.json")["scope"]["write_paths"] != metadata["write_paths"]):
                raise ValueError("repository-task run lacks its fixed task scope")
            denied = snapshot.json("evidence/task-scope.json")["scope"].get("deny_read_paths", [])
            if not any(Path(root).is_absolute() and task.root.is_relative_to(Path(root)) for root in denied):
                raise ValueError("repository-task scope does not protect private task assets")
            if (observation["repository"] != str(repository)
                    or spec["repository"]["commit"] != metadata["commit"]
                    or spec["task"].encode() != task_text(task, toolchain, metadata.get("task_just")).encode()):
                raise ValueError("run does not match repository task")
        before = inventory(repository, candidate=True)
        patch, git_metadata = capture_diff(repository, metadata["commit"])
        result = grade(repository, sandbox, task, toolchain)
        violations = scope_changes(metadata["files"], before, task.manifest["write_paths"])
        if inventory(repository, candidate=True) != before or capture_diff(repository, metadata["commit"]) != (patch, git_metadata):
            raise ValueError("candidate changed during evaluation")
        if snapshot is not None:
            snapshot.verify_unchanged()
            current, _, _ = observe_terminal(Path(run))
            if current.hashes != snapshot.hashes:
                raise ValueError("run changed during evaluation")
        result.update(schema_version=1, fixture=task.name, **task.facets(),
                      scope_violations=violations, scope_success=not violations,
                      candidate_files=before, fixture_commit=metadata["commit"])
        result["task_success"] = result["task_success"] and not violations
        output.mkdir(exist_ok=False)
        (output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
        (output / "candidate.diff").write_bytes(patch)
        if observation is not None:
            (output / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository", "sandbox", "output", "fixture-manifest"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--toolchain", type=Path)
    args = parser.parse_args()
    result = evaluate(args.repository, args.sandbox, args.output, args.fixture_manifest, args.run, args.toolchain)
    print(json.dumps({"fixture": result["fixture"], "task_success": result["task_success"]}))


if __name__ == "__main__":
    main()
