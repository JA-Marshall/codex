"""Capture stopped product bytes independently of workflow commits and ignores."""

import hashlib
import json
from pathlib import Path

from task_registry import relative_path, MAX_TOTAL
from workflows.bmad_install import inventory


def capture_product(
    workspace, destination, *, starter, write_paths, runtime, installation=None
):
    """Keep all evidence, but expose only validated product bytes to the grader."""
    if (
        runtime.get("process", {}).get("stop_status") != "confirmed"
        or runtime.get("provider_handlers_stopped") is not True
    ):
        raise ValueError("candidate capture requires confirmed run shutdown")
    workspace, destination = Path(workspace).resolve(), Path(destination).resolve()
    if destination.is_relative_to(workspace) or workspace.is_relative_to(destination):
        raise ValueError("snapshot must be outside the candidate")
    if not write_paths:
        raise ValueError("explicit product write roots required")
    for name in write_paths:
        relative_path(workspace, name)
    excluded = [".git"]
    controls = {}
    if installation is not None:
        if installation.workspace != workspace:
            raise ValueError("installation belongs to another candidate")
        installation.verify()
        excluded.extend(installation.manifest["protected"])
        for name in installation.manifest["control_paths"]:
            directory = relative_path(workspace, name)
            controls[name] = inventory(directory)
            for relative, metadata in controls[name].items():
                path = directory / relative
                # Data artifacts can contain code excerpts, but never become a
                # hidden runtime dependency: this namespace is absent in grading.
                if path.suffix.lower() not in (
                    ".md",
                    ".txt",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".toml",
                    ".diff",
                    ".patch",
                    ".csv",
                    ".log",
                ):
                    raise ValueError("unsupported control artifact type")
                path.read_bytes().decode("utf-8")
            excluded.append(name)
    product = inventory(workspace, exclude=excluded, max_total=MAX_TOTAL)
    changed = sorted(
        name
        for name in starter.keys() | product.keys()
        if starter.get(name) != product.get(name)
    )
    violations = [
        name
        for name in changed
        if not any(name == root or name.startswith(root + "/") for root in write_paths)
    ]
    # Scope violations are evidence of a candidate failure, not an omitted file.
    destination.mkdir(parents=True, exist_ok=False)
    for name, metadata in product.items():
        content = (workspace / name).read_bytes()
        if (
            len(content) != metadata["size"]
            or hashlib.sha256(content).hexdigest() != metadata["sha256"]
        ):
            raise ValueError("candidate changed during capture")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if (
        inventory(destination, max_total=MAX_TOTAL) != product
        or inventory(workspace, exclude=excluded, max_total=MAX_TOTAL) != product
    ):
        raise ValueError("candidate snapshot is inconsistent")
    return {
        "schema_version": 1,
        "product": product,
        "controls": controls,
        "candidate_sha256": hashlib.sha256(
            json.dumps(product, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "changed_paths": changed,
        "scope_violations": violations,
    }
