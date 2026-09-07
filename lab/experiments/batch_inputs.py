"""Bounded, isolated batch inputs; the child host still validates prepared data."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def read_json(path, limit=65536):
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("batch input exceeds size limit")
    return json.loads(data), hashlib.sha256(data).hexdigest()


def fingerprint(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def load_batch(path, output, jobs, purpose="throughput"):
    if purpose not in ("throughput", "isolated-timing"):
        raise ValueError("unknown measurement purpose")
    if purpose == "isolated-timing" and jobs != 1:
        raise ValueError(
            "isolated-timing requires jobs=1; parallel runs measure shared throughput"
        )
    path = path.resolve(strict=True)
    manifest, manifest_hash = read_json(path)
    if set(manifest) - {"schema_version", "binary", "binary_sha256", "runs"}:
        raise ValueError("unknown batch manifest field")
    if manifest.get("schema_version") != 1 or not 1 <= jobs <= 32:
        raise ValueError("schema_version must be 1; jobs must be 1..32")
    runs = manifest["runs"]
    if not isinstance(runs, list) or not 1 <= len(runs) <= 32:
        raise ValueError("batch requires 1..32 runs")
    binary = (path.parent / manifest["binary"]).resolve(strict=True)
    binary_hash = fingerprint(binary)
    if manifest.get("binary_sha256", binary_hash) != binary_hash:
        raise ValueError("batch binary changed")
    ids, repositories, git_dirs, destinations, entries = set(), [], set(), [], []
    protected = [path, binary]
    for run in runs:
        if set(run) - {"run_id", "prepared", "prepared_sha256"}:
            raise ValueError("unknown run field")
        name = run["run_id"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name)
            or name in ids
        ):
            raise ValueError("invalid or duplicate run ID")
        ids.add(name)
        prepared = (path.parent / run["prepared"]).resolve(strict=True)
        descriptor, digest = read_json(prepared)
        if run.get("prepared_sha256", digest) != digest:
            raise ValueError("prepared descriptor changed")
        repository = Path(descriptor["repository"]).resolve(strict=True)
        git_dir = Path(
            subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "--absolute-git-dir"],
                text=True,
                timeout=10,
            ).strip()
        ).resolve(strict=True)
        if git_dir in git_dirs or any(
            repository.is_relative_to(p) or p.is_relative_to(repository)
            for p in repositories
        ):
            raise ValueError("conditions require distinct non-overlapping checkouts")
        git_dirs.add(git_dir)
        repositories.append(repository)
        destination = Path(descriptor["runs_directory"]).resolve(strict=True) / name
        if destination.exists() or destination in destinations:
            raise ValueError("execution destination already exists or is duplicated")
        destinations.append(destination)
        protected.extend(
            [
                prepared.parent.parent,
                Path(descriptor["codex_home"]).resolve(strict=True),
            ]
        )
        entries.append(
            {
                "run_id": name,
                "prepared": str(prepared),
                "prepared_sha256": digest,
                "repository": str(repository),
                "artifacts": str(destination),
            }
        )
    output = output.resolve()
    protected.extend(repositories + destinations)
    if output.exists() or any(
        output.is_relative_to(p) or p.is_relative_to(output) for p in protected
    ):
        raise ValueError("batch output exists or overlaps protected inputs/checkouts")
    if any(
        d.is_relative_to(r) or r.is_relative_to(d)
        for d in destinations
        for r in repositories
    ):
        raise ValueError("run artifacts overlap a task checkout")
    return {
        "schema_version": 1,
        "manifest_sha256": manifest_hash,
        "binary": str(binary),
        "binary_sha256": binary_hash,
        "jobs": jobs,
        "measurement_purpose": purpose,
        "phase_timeout_clock": "wall_clock_including_provider_queue",
        "max_hosts": 32,
        "runs": entries,
        "scheduler_sha256": {
            name: fingerprint(Path(__file__).with_name(name))
            for name in ("run_batch.py", "batch_inputs.py")
        },
        "python": {
            "path": sys.executable,
            "version": sys.version,
            "sha256": fingerprint(Path(sys.executable)),
        },
    }
