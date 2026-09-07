"""Validate task-scope evidence without restoring any execution authority."""

import hashlib
import json
import re
from pathlib import Path


def bind(snapshot, event):
    fingerprint = event.get("scope_sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("invalid scope digest")
    evidence = snapshot.json("evidence/task-scope.json")
    scope = evidence["scope"]
    canonical = {"schema_version": scope["schema_version"], "write_paths": scope["write_paths"],
                 "deny_read_paths": scope.get("deny_read_paths", []), "read_paths": scope.get("read_paths", [])}
    digest = hashlib.sha256(json.dumps(canonical, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    policy = snapshot.json("evidence/campaign-policy.json")
    selected = dict(policy["task_scope"])
    selected.setdefault("deny_read_paths", [])
    selected.setdefault("read_paths", [])
    if digest != fingerprint or evidence["scope_sha256"] != digest or scope != selected:
        raise ValueError("scope definition does not match campaign authority")
    return fingerprint


def record(active, event, fingerprint):
    if fingerprint is None:
        raise ValueError("scope phase has no bound authority")
    evidence = event.get("evidence", {})
    if evidence.get("scope_sha256") != fingerprint:
        raise ValueError("scope phase digest mismatch")
    if event["type"] == "phase_scope_permissions":
        if "scope_permissions" in active or "thread_id" in active or evidence.get("phase") != active["phase"]:
            raise ValueError("invalid scope permissions ordering")
        if active["phase"] != "implementation" and evidence.get("candidate_write_paths") != []:
            raise ValueError("read-only phase received candidate write paths")
        active["scope_permissions"] = evidence
    else:
        if "scope_permissions" not in active or "scope_audit" in active or "thread_id" not in active:
            raise ValueError("invalid scope audit ordering")
        if type(evidence.get("authorized")) is not bool:
            raise ValueError("missing scope audit decision")
        if active["phase"] != "implementation" and evidence["authorized"] and evidence.get("candidate_unchanged") is not True:
            raise ValueError("read-only phase changed candidate")
        active["scope_audit"] = evidence


def verify_phase(phase, output, configured, terminal_state, definition):
    permissions = phase["scope_permissions"]
    audit = phase["scope_audit"]
    if output.get("task_scope") != dict(permissions, audit=audit):
        raise ValueError("phase scope artifacts differ from journal")
    if configured.get("permission_profile") != permissions["permission_profile"]:
        raise ValueError("upstream phase permissions differ from scope")
    expected_candidate = [str(Path(configured["cwd"]) / path) for path in definition["write_paths"]] if phase["phase"] == "implementation" else []
    if permissions["candidate_write_paths"] != expected_candidate:
        raise ValueError("phase write paths differ from fixed task scope")
    profile = permissions["permission_profile"]
    if profile.get("type") != "managed" or profile.get("network") != "restricted" or profile.get("file_system", {}).get("type") != "restricted":
        raise ValueError("scope requires managed restricted permissions")
    writes = []
    denied = []
    for entry in profile["file_system"]["entries"]:
        if entry["access"] == "write":
            if entry["path"].get("type") != "path":
                raise ValueError("scope has a symbolic writable root")
            writes.append(entry["path"]["path"])
        elif entry["access"] == "deny" and entry["path"].get("type") == "path":
            denied.append(entry["path"]["path"])
    expected_writes = expected_candidate + ([permissions["scratch"]] if phase["phase"] in ("implementation", "verification") else [])
    if sorted(writes) != sorted(expected_writes):
        raise ValueError("scope has unexpected writable roots")
    declared_denied = permissions.get("deny_read_paths", [])
    if (not set(definition.get("deny_read_paths", [])).issubset(declared_denied)
            or not set(declared_denied).issubset(denied)):
        raise ValueError("scope private-read denial is not enforced")
    if terminal_state == "completed" and not audit["authorized"]:
        raise ValueError("completed run has unauthorized scope changes")
