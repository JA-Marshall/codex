"""Explicit new-campaign storage admission and post-shutdown debug retention."""

import hashlib
import json
import os
from pathlib import Path
import shutil


def policy(value, run_ids=None):
    if not isinstance(value, dict) or set(value) != {
        "max_bytes",
        "reserve_per_active_trial",
        "min_free_bytes",
        "debug_bytes_per_trial",
        "full_trace_sample",
    }:
        raise ValueError("explicit bounded storage policy required")
    if any(
        type(value[name]) is not int or value[name] < 0
        for name in (
            "max_bytes",
            "reserve_per_active_trial",
            "min_free_bytes",
            "debug_bytes_per_trial",
        )
    ):
        raise ValueError("storage limits must be nonnegative integers")
    if (
        min(
            value["max_bytes"],
            value["reserve_per_active_trial"],
            value["debug_bytes_per_trial"],
        )
        <= 0
    ):
        raise ValueError("positive campaign, reservation and debug bounds required")
    sample = value["full_trace_sample"]
    if (
        not isinstance(sample, list)
        or len(sample) > 1000
        or any(not isinstance(identity, str) for identity in sample)
    ):
        raise ValueError("bounded predeclared trace sample required")
    if len(set(sample)) != len(sample) or (
        run_ids is not None and not set(sample) <= set(run_ids)
    ):
        raise ValueError("trace sample must contain unique planned run IDs")
    return value


def disk_admission(manifest, active):
    if "storage_policy" not in manifest:
        return {"admit": True, "policy": "historical manifest; unchanged behavior"}
    limits = policy(
        manifest["storage_policy"], [trial["run_id"] for trial in manifest["trials"]]
    )
    root = Path(manifest["output"]).resolve(strict=True)
    size, count = 0, 0
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_file():
            size += path.stat().st_size
            count += 1
            if count > 250000:
                return {"admit": False, "reason": "storage_inventory_limit"}
    reserved = (active + 1) * limits["reserve_per_active_trial"]
    free = shutil.disk_usage(root).free
    return {
        "admit": size + reserved <= limits["max_bytes"]
        and free >= reserved + limits["min_free_bytes"],
        "used_bytes": size,
        "reserved_bytes": reserved,
        "free_bytes": free,
        "reason": "disk_admission_limit",
        "semantics": "admission ceiling; running output may exceed its reservation, not a filesystem quota",
    }


def retain_debug(manifest, entry, record):
    if "storage_policy" not in manifest:
        return None
    limits = policy(
        manifest["storage_policy"], [trial["run_id"] for trial in manifest["trials"]]
    )
    observed = record.get("workflow_result") or {}
    runtime = (observed.get("evidence") or {}).get("runtime") or {}
    if not runtime:
        return {
            "action": "retained",
            "reason": "retention targets SDK debug artifacts only; legacy evidence preserved",
        }
    if (
        observed.get("stop_status") != "confirmed"
        or runtime.get("provider_handlers_stopped") is not True
    ):
        return {"action": "retained", "reason": "shutdown not confirmed; no deletion"}
    runs = (Path(manifest["output"]) / "runs").resolve(strict=True)
    root = (runs / entry["run_id"]).resolve(strict=True)
    if root.parent != runs or root.name != entry["run_id"]:
        raise ValueError("retention requires a direct owned run directory")
    receipt_path = root / "retention.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["policy"] != limits:
            raise ValueError("existing retention policy differs")
        # An interrupted deletion is evidence, not permission to retry it silently.
        return receipt
    selected = (
        record.get("task_success") is not True
        or observed.get("workflow_status") != "completed"
        or entry["run_id"] in limits["full_trace_sample"]
    )
    remaining = limits["debug_bytes_per_trial"] if selected else 0
    groups = []
    for home in sorted(root.glob("**/session/home")):
        if home.is_symlink() or not home.resolve().is_relative_to(root):
            raise ValueError("debug home escaped owned run")
        directory = home / "sessions"
        if directory.exists():
            if directory.is_symlink():
                raise ValueError("debug sessions directory is a symlink")
            groups.extend([path] for path in sorted(directory.rglob("*.jsonl")))
        # SQLite database + WAL + SHM form one artifact. Keep or drop the whole
        # group; a truncated database is not a usable diagnostic artifact.
        database = [
            home / name
            for name in ("logs_2.sqlite", "logs_2.sqlite-wal", "logs_2.sqlite-shm")
        ]
        groups.append([path for path in database if path.exists()])
    files = []
    for group in groups:
        rows = []
        for path in group:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("debug retention path escaped owned run")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            rows.append(
                {
                    "path": str(path.relative_to(root)),
                    "before_bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
        size = sum(row["before_bytes"] for row in rows)
        keep = size <= remaining
        if keep:
            remaining -= size
        for row in rows:
            row.update(
                action="keep" if keep else "delete",
                retained_bytes=row["before_bytes"] if keep else 0,
            )
        files.extend(rows)
    receipt = {
        "policy": limits,
        "debug_retention_selected": selected,
        "all_selected_debug_retained": selected
        and all(row["action"] == "keep" for row in files),
        "files": files,
        "status": "planned",
        "essential_evidence_untouched": True,
        "scope": "session rollout JSONL and logs_2 SQLite groups only; state databases and all other files retained",
    }
    # Persist the complete plan before any destructive operation. A crash leaves
    # an explicit incomplete receipt with hashes, never an unexplained deletion.
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    for row in files:
        if row["action"] == "delete":
            path = root / row["path"]
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError("debug file changed after shutdown inventory")
            path.unlink()
    receipt["status"] = "completed"
    temporary = receipt_path.with_suffix(".json.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(receipt_path)
    return receipt
