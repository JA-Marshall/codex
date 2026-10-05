"""Load versioned repository tasks without executing task-provided Python code."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys

from setup_fixture import git, sha256

FAMILIES = ("greenfield", "extension", "bug_fix", "maintenance")
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")


def relative_path(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("invalid task-relative path")
    parts = name.split("/")
    if any(part in ("", ".", "..", ".git") for part in parts) or ":" in name:
        raise ValueError("escaping or protected task-relative path")
    path = Path(root)
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("linked task path")
    return path


def inventory(root, *, candidate=False, hash_files=True):
    """Bound all source files, not just one extension; reject filesystem aliases."""
    root = Path(root)
    result, total, visited = {}, 0, 0
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            visited += 1
            if visited > 4096:
                raise ValueError("task inventory exceeds entry limit")
            if candidate and path.parent == root and path.name == ".git":
                continue
            if path.name == "__pycache__" or path.suffix == ".pyc":
                continue
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                total += metadata.st_size
                if metadata.st_size > MAX_FILE or total > MAX_TOTAL:
                    raise ValueError("task file inventory exceeds byte limits")
                result[path.relative_to(root).as_posix()] = (
                    sha256(path) if hash_files else None
                )
            else:
                raise ValueError("task inventory contains a link or special file")
            if len(result) + len(pending) > 2048:
                raise ValueError("task inventory exceeds file limit")
    return result


def read_json(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_FILE:
        raise ValueError("task JSON exceeds byte limit")
    return json.loads(data)


@dataclass(frozen=True)
class Task:
    root: Path
    manifest: dict

    @property
    def name(self):
        return self.manifest["id"]

    def facets(self):
        return {
            **{
                key: self.manifest[key]
                for key in ("track", "evaluation_group", "pressure")
                if key in self.manifest
            },
            **{
                key: self.manifest[key]
                for key in (
                    "family",
                    "language",
                    "size",
                    "split",
                    "project_id",
                    "capabilities",
                )
            },
        }


def load_task(root):
    root = Path(root).resolve(strict=True)
    files = inventory(root)
    data = read_json(root / "manifest.json")
    if (
        data.get("schema_version") not in (1, 2)
        or not IDENTIFIER.fullmatch(data.get("id", ""))
        or not IDENTIFIER.fullmatch(data.get("project_id", ""))
        or data.get("family") not in FAMILIES
        or data.get("language") not in ("python", "rust")
        or data.get("size") not in ("small", "medium", "large")
        or data.get("split") not in ("development", "study", "confirmation")
    ):
        raise ValueError("invalid task identity or classification")
    if not isinstance(data.get("capabilities"), list) or not data["capabilities"]:
        raise ValueError("task capabilities must be declared")
    for name in ("command", "build", "public_command"):
        value = data.get(name)
        if (
            not isinstance(value, list)
            or len(value) > 32
            or any(
                not isinstance(arg, str) or not arg or len(arg) > 4096 or "\0" in arg
                for arg in value
            )
            or (not value and name != "build")
        ):
            raise ValueError("task commands must be bounded argument arrays")
    if data.get("structural_checks", []) != []:
        raise ValueError("unsupported structural grading rule")
    writes = data.get("write_paths")
    if (
        not isinstance(writes, list)
        or not 1 <= len(writes) <= 16
        or sum(map(len, writes)) > 1024
    ):
        raise ValueError("task must declare bounded write paths")
    for name in writes:
        if len(name) > 128 or any(
            part.lower()
            in (".codex", ".agents", ".openai", "agents.md", "task.md", "contract.md")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
            for part in name.split("/")
        ):
            raise ValueError("unsafe or protected task write path")
        if not relative_path(root / "project", name).exists():
            raise ValueError(
                "task write roots must exist; allow new files in a directory"
            )
    if any(
        a == b or a.startswith(b + "/") or b.startswith(a + "/")
        for index, a in enumerate(writes)
        for b in writes[index + 1 :]
    ):
        raise ValueError("overlapping task write roots")
    for name in ("TASK.md", "private/cases.json"):
        if name not in files:
            raise ValueError("task contract and private cases are required")
    mutants = data.get("mutants")
    if not isinstance(mutants, list) or not 2 <= len(mutants) <= 8:
        raise ValueError("task requires two or more calibration mutants")
    for name in mutants:
        if not IDENTIFIER.fullmatch(name) or not (root / "mutants" / name).is_dir():
            raise ValueError("invalid calibration mutant")
    alternatives = data.get("valid_alternatives", [])
    if (
        not isinstance(alternatives, list)
        or len(alternatives) > 8
        or any(
            not isinstance(name, str)
            or not IDENTIFIER.fullmatch(name)
            or name in ("baseline", "solution", "irrelevant-patch", *mutants)
            or not (root / "alternatives" / name).is_dir()
            for name in alternatives
        )
        or len(set(alternatives)) != len(alternatives)
    ):
        raise ValueError("invalid positive calibration alternative")
    if not (root / "solution").is_dir():
        raise ValueError("task reference solution is missing")
    if data["schema_version"] == 2:
        from task_v2 import TaskSpecV2

        TaskSpecV2.load(root, data)
    return Task(root, data)


def discover(root, *, allowed_splits=None):
    root = Path(root).resolve(strict=True)
    inventory(root, hash_files=allowed_splits is None)
    tasks, projects, pending, selected = {}, {}, [root], []
    while pending:
        directory = pending.pop()
        if not (directory / "manifest.json").is_file():
            pending.extend(
                sorted(path for path in directory.iterdir() if path.is_dir())
            )
            continue
        if (
            allowed_splits is not None
            and read_json(directory / "manifest.json").get("split")
            not in allowed_splits
        ):
            raise ValueError("task root contains a forbidden held-out split")
        selected.append(directory)
    # Check every manifest before reading any pack contents in a tuning call.
    for directory in selected:
        task = load_task(directory)
        if task.name in tasks:
            raise ValueError("duplicate task ID")
        project, split = task.manifest["project_id"], task.manifest["split"]
        if project in projects and projects[project] != split:
            raise ValueError("project ancestry cannot span task splits")
        projects[project] = split
        tasks[task.name] = task
    if not tasks or len(tasks) > 1000:
        raise ValueError("task library must contain 1..1000 tasks")
    return tasks


def evaluator_fingerprint():
    names = (
        "task_registry.py",
        "task_sandbox.py",
        "evaluate_task.py",
        "scope_observation.py",
        "terminal_run.py",
        "setup_fixture.py",
        "task_v2.py",
    )
    return {name: sha256(Path(__file__).with_name(name)) for name in names}


def task_text(task, toolchain=None, task_just=None):
    text = (task.root / "TASK.md").read_text()
    if task.manifest["language"] == "python":
        text += (
            f"\nHarness execution environment: use {Path(sys.executable).resolve()} "
            "for Python commands and tests. Use the supplied scratch directory for temporary files; "
            "do not install dependencies or create bytecode files in the repository.\n"
        )
    elif toolchain is not None:
        tools = Path(toolchain) / "bin"
        text += (
            f"\nHarness execution environment: use {tools / 'cargo'} with "
            f"RUSTC={tools / 'rustc'} and RUSTDOC={tools / 'rustdoc'}. "
            "Use the host-provided CARGO_HOME and CARGO_TARGET_DIR scratch paths. "
            "Run Cargo offline and locked; do not download dependencies or write build output into the repository.\n"
        )
        if task_just is not None:
            command = (
                f'PATH={shlex.quote(str(tools))}:"$PATH" '
                f"RUSTC={shlex.quote(str(tools / 'rustc'))} "
                f"RUSTDOC={shlex.quote(str(tools / 'rustdoc'))} "
                f"{shlex.quote(str(task_just))} --justfile justfile test"
            )
            text += (
                "\nThe just executable is a frozen campaign input. Run the public test recipe "
                "from the repository with the exact pinned tools:\n\n"
                f"```sh\n{command}\n```\n"
            )
    return text


def setup(destination, task, toolchain=None, task_just=None):
    destination = Path(destination).resolve()
    destination.mkdir(exist_ok=False)
    repository = destination / "repository"
    shutil.copytree(
        task.root / "project",
        repository,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (repository / "TASK.md").write_text(task_text(task, toolchain, task_just))
    files = inventory(repository)
    git(repository, "init", "--quiet", "--initial-branch=main", "--object-format=sha1")
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", task.name + " baseline")
    metadata = {
        "schema_version": 1,
        "kind": "repository_task",
        "fixture": task.name,
        "repository": str(repository),
        "commit": git(repository, "rev-parse", "HEAD"),
        "task_root": str(task.root),
        "task_sha256": sha256(repository / "TASK.md"),
        "task_toolchain": str(toolchain) if toolchain is not None else None,
        "task_just": str(task_just) if task_just is not None else None,
        "assets": inventory(task.root),
        "files": files,
        "evaluator": evaluator_fingerprint(),
        "python_sha256": sha256(Path(sys.executable).resolve()),
        "write_paths": task.manifest["write_paths"],
        **task.facets(),
    }
    (destination / "fixture.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata
