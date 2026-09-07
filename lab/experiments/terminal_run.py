"""Read terminal evidence without restoring authority or changing source journals."""

import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile

MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


class RunSnapshot:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.hashes = {}
        self.bytes = 0

    def read(self, name: str) -> bytes:
        path = self.root
        for component in name.split("/"):
            if component in ("", ".", ".."):
                raise ValueError("unsafe artifact path")
            path = path / component
            if path.is_symlink():
                raise ValueError("linked run artifact")
        if not path.resolve().is_relative_to(self.root) or not path.is_file():
            raise ValueError("escaping or missing run artifact")
        with path.open("rb") as source:
            data = source.read(MAX_FILE + 1)
        self.bytes += len(data)
        if len(data) > MAX_FILE or self.bytes > MAX_TOTAL:
            raise ValueError("run evidence exceeds bounds")
        self.hashes[name] = hashlib.sha256(data).hexdigest()
        return data

    def json(self, name: str):
        return json.loads(self.read(name))

    def journal(self, name: str):
        data = self.read(name)
        if data and not data.endswith(b"\n"):
            raise ValueError("partial run journal")
        events = [json.loads(line) for line in data.splitlines()]
        if any(
            e.get("sequence") != i + 1 or e.get("schema_version") != 1
            for i, e in enumerate(events)
        ):
            raise ValueError("invalid journal sequence or version")
        return events

    def verify_unchanged(self):
        # A fresh bounded reader rechecks symlinks and every observed digest.
        current = RunSnapshot(self.root)
        for name, expected in self.hashes.items():
            if hashlib.sha256(current.read(name)).hexdigest() != expected:
                raise ValueError("run changed during observation")


def observe_terminal(run: Path):
    snapshot = RunSnapshot(run)
    events = snapshot.journal("events.jsonl")
    if not events or events[-1].get("state") not in ("completed", "failed"):
        raise ValueError("run is not terminal completed or failed")
    runtime = snapshot.journal("runtime-events.jsonl")
    phases, active, calls, threads = [], None, set(), set()
    faulted = False
    for event in runtime:
        kind = event.get("type")
        if kind == "phase_started":
            if active is not None or faulted or event.get("epoch") != len(phases) + 1:
                raise ValueError("invalid phase start")
            if len(phases) >= 32 or event.get("phase") not in (
                "research",
                "planning",
                "implementation",
                "verification",
            ):
                raise ValueError("unsupported phase")
            active = dict(event)
        elif kind == "runtime_failed":
            if (
                active is not None
                or calls
                or event.get("phase_retained") is not False
                or event.get("active_dispatches") != 0
            ):
                raise ValueError("failed run has unconfirmed shutdown")
            faulted = True
        else:
            if active is None or event.get("epoch") != active["epoch"]:
                raise ValueError("runtime event outside active phase")
            if kind == "phase_thread_bound":
                thread = event.get("thread_id")
                if not thread or thread in threads or "thread_id" in active:
                    raise ValueError("invalid phase thread binding")
                threads.add(thread)
                active["thread_id"] = thread
            elif kind in ("tool_admitted", "tool_finished"):
                call = (event.get("turn_id"), event.get("call_id"))
                if not all(call) or "thread_id" not in active:
                    raise ValueError("invalid tool identity")
                if kind == "tool_admitted":
                    if call in calls or event.get("thread_id") != active["thread_id"]:
                        raise ValueError("duplicate or foreign tool")
                    calls.add(call)
                else:
                    if call not in calls:
                        raise ValueError("unmatched tool completion")
                    calls.remove(call)
            elif kind == "admission_revoked":
                pass  # Amendment revocation alone is not a shutdown receipt.
            elif kind == "phase_stopped":
                if calls or "thread_id" not in active:
                    raise ValueError("incomplete phase shutdown")
                phases.append(active)
                active = None
            else:
                raise ValueError("unsupported runtime event")
    if active is not None or calls:
        raise ValueError("missing phase shutdown")
    totals = {
        key: 0 for key in ("input_tokens", "output_tokens", "cached_input_tokens")
    }
    repositories = set()
    for index, phase in enumerate(phases, 1):
        snapshot.json(f"evidence/input-{index:02}.json")
        output = snapshot.json(f"evidence/phase-{index:02}.json")
        if output.get("thread_id") != phase["thread_id"] or not any(
            e.get("msg", {}).get("type") == "shutdown_complete"
            for e in output.get("events", [])
        ):
            raise ValueError("missing or foreign phase shutdown artifact")
        configured = [
            e["msg"]
            for e in output["events"]
            if e.get("msg", {}).get("type") == "session_configured"
        ]
        if (
            len(configured) != 1
            or configured[0].get("session_id") != phase["thread_id"]
            or not configured[0].get("cwd")
        ):
            raise ValueError("missing phase repository binding")
        repositories.add(str(Path(configured[0]["cwd"]).resolve()))
        usage = (output.get("token_usage") or {}).get("total_token_usage", {})
        for key in totals:
            value = usage.get(key)
            totals[key] = (
                totals[key] + value
                if totals[key] is not None and type(value) is int and value >= 0
                else None
            )
    expected = {f"phase-{index:02}.json" for index in range(1, len(phases) + 1)}
    if {p.name for p in (snapshot.root / "evidence").glob("phase-*.json")} != expected:
        raise ValueError("unexpected phase artifact inventory")
    expected_inputs = {name.replace("phase-", "input-") for name in expected}
    if {
        p.name for p in (snapshot.root / "evidence").glob("input-*.json")
    } != expected_inputs:
        raise ValueError("unexpected phase input inventory")
    spec = snapshot.json("config/run-spec.json")
    if len(repositories) != 1:
        raise ValueError("missing or inconsistent run repository")
    decisions = [
        e["change"]["type"]
        for e in events
        if e["change"]["type"] in ("human_approved", "human_rejected", "plan_edited")
    ]
    observation = {
        "schema_version": 1,
        "run": str(snapshot.root),
        "workflow_state": events[-1]["state"],
        "terminal_change": events[-1]["change"],
        "all_started_phases_shutdown": True,
        "repository": next(iter(repositories)),
        "first_plan_human_approval": decisions[0] == "human_approved"
        if decisions
        else None,
        "phase_turns": len(phases),
        "planner_phases": sum(p["phase"] == "planning" for p in phases),
        "tool_admissions": sum(e["type"] == "tool_admitted" for e in runtime),
        "usage": totals,
        "workflow_terminal_elapsed_ms": events[-1].get("elapsed_ms"),
        "human_plan_edits": sum(e["change"]["type"] == "plan_edited" for e in events),
        "plan_amendments": sum(
            e["change"]["type"] == "amendment_requested" for e in events
        ),
        "plan_deviations": None,
        "source_artifact_sha256": snapshot.hashes,
        "authority_restored": False,
    }
    return snapshot, spec, observation


def capture_diff(repository: Path, baseline: str):
    """Bounded Git subprocess adapter; no index, checkout or commit mutations."""

    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE, MAX_FILE))

    def command(*args):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=" + os.devnull, *args],
                cwd=repository,
                env={
                    "PATH": os.defpath,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                },
                stdout=out,
                stderr=err,
                timeout=20,
                check=False,
                preexec_fn=limits,
            )
            out.seek(0)
            data = out.read(MAX_FILE + 1)
            allowed = (0, 1) if "--no-index" in args else (0,)
            if result.returncode not in allowed or len(data) >= MAX_FILE:
                raise ValueError("Git observation failed or exceeded bounds")
            return data

    if command("rev-parse", "HEAD").decode().strip() != baseline:
        raise ValueError("candidate HEAD changed")
    options = ("--no-ext-diff", "--no-textconv", "--no-renames")
    tracked = (
        command("diff", *options, "--name-only", "-z", baseline, "--")
        .decode()
        .split("\0")
    )
    untracked = (
        command("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    )
    names = sorted(set(tracked + untracked) - {""})
    if len(names) > 128:
        raise ValueError("too many changed files")
    patch = command("diff", *options, "--binary", baseline, "--")
    for name in filter(None, untracked):
        path = repository / name
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(repository)
        ):
            raise ValueError("unsafe untracked file")
        patch += command(
            "diff", "--no-index", *options, "--binary", "--", os.devnull, name
        )
        if len(patch) > MAX_FILE:
            raise ValueError("diff exceeds bounds")
    return patch, {
        "base_commit": baseline,
        "final_commit": baseline,
        "files_changed": len(names),
        "changed_files": names,
        "diff_bytes": len(patch),
        "diff_sha256": hashlib.sha256(patch).hexdigest(),
    }
