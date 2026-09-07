"""Optional repository-task inputs for the existing finite campaign scheduler."""

from pathlib import Path
import os
import shutil

from task_registry import discover


def selections(args, legacy_names):
    root = getattr(args, "task_root", None)
    tasks = discover(root) if root is not None else {}
    if set(tasks) & set(legacy_names):
        raise ValueError("repository task IDs must not shadow legacy fixtures")
    unknown = set(args.fixture) - set(legacy_names) - set(tasks)
    if unknown:
        raise ValueError("unknown task selection: " + ", ".join(sorted(unknown)))
    selected = {name: tasks[name] for name in args.fixture if name in tasks}
    toolchain = getattr(args, "task_toolchain", None)
    if any(task.manifest["language"] == "rust" for task in selected.values()):
        if toolchain is None:
            raise ValueError("Rust task campaigns require --task-toolchain")
        toolchain = toolchain.resolve(strict=True)
        for name in ("cargo", "rustc", "rustdoc"):
            if not (toolchain / "bin" / name).is_file():
                raise ValueError("Rust toolchain is incomplete")
    return selected, toolchain


def archive_tasks(archive, tasks):
    if not tasks:
        return {}
    root = archive / "tasks"
    root.mkdir()
    for name, task in tasks.items():
        shutil.copytree(task.root, root / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return {"task_root": str(root), "task_ids": sorted(tasks)}


def just_helper(args, tasks):
    requested = getattr(args, "task_just", None)
    if not any(task.manifest["language"] == "rust" for task in tasks.values()):
        if requested is not None:
            raise ValueError("--task-just requires a Rust repository task")
        return None
    if requested is None:
        raise ValueError("Rust task campaigns require --task-just")
    executable = Path(requested).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("task just helper must be an executable file")
    task_root = Path(args.task_root).resolve(strict=True)
    if executable.is_relative_to(task_root) or task_root.is_relative_to(executable):
        raise ValueError("task just helper must not overlap task assets")
    return executable


def archive_just(archive, executable):
    if executable is None:
        return {}
    directory = archive / "task-tools"
    directory.mkdir()
    destination = directory / "just"
    shutil.copy2(executable, destination)
    return {"task_just": str(destination)}


def toolchain_pins(toolchain):
    if toolchain is None:
        return []
    # Pin compiler/linker tools and target libraries, not only the cargo launcher.
    return [path for folder in ("bin", "lib", "libexec")
            for path in (Path(toolchain) / folder).rglob("*") if path.is_file()]
