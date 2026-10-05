"""Optionally pin a standalone Python installation, including task dependencies."""

from pathlib import Path
import sys


def runtime_files(root):
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            raise ValueError("Pinned Python runtime must not contain bytecode caches")
        if path.is_symlink():
            raise ValueError("Pinned Python runtime must not contain symbolic links")
        if path.is_file():
            files.append(path)
    return files


def freeze_python_runtime(requested):
    if requested is None:
        return {}, []
    root = Path(requested).resolve(strict=True)
    if (
        root != Path(sys.base_prefix).resolve()
        or Path(sys.prefix).resolve() != root
        or not Path(sys.executable).resolve().is_relative_to(root)
    ):
        raise ValueError(
            "Python runtime must be the active standalone interpreter prefix"
        )
    files = runtime_files(root)
    return {
        "python_runtime": {
            "root": str(root),
            "files": [path.relative_to(root).as_posix() for path in files],
        }
    }, files


def validate_python_runtime(manifest):
    declared = manifest.get("python_runtime")
    if declared is None:
        return
    root = Path(declared["root"])
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Python runtime must have a canonical absolute root")
    files = runtime_files(root)
    if (
        [path.relative_to(root).as_posix() for path in files] != declared["files"]
        or not Path(manifest["python"]).resolve(strict=True).is_relative_to(root)
        or any(str(path) not in manifest["pins"] for path in files)
    ):
        raise ValueError("Python runtime inventory differs from the frozen campaign")
