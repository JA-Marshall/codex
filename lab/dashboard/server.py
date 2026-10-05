#!/usr/bin/env python3
"""Local, read-only views of campaign receipts; never imports the experiment runner."""

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
QUIET_MS = 120_000
MAX_BYTES = 16 * 1024 * 1024
STATIC = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


def number(value):
    return value if type(value) is int and value >= 0 else None


def label(value):
    return value[:200] if isinstance(value, str) else None


def boolean(value):
    return value if type(value) is bool else None


def objects(value):
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def duration(start, end):
    return max(0, end - start) if start is not None and end is not None else None


class CampaignStore:
    def __init__(self, campaign_root, timing_root):
        self.root = Path(campaign_root).expanduser().resolve()
        self.timing_root = Path(timing_root).expanduser().resolve()
        self.cache = {}
        self.lock = Lock()

    def read(self, base, path, lines=False):
        """Only read contained regular files, caching stable snapshots of bounded size."""
        empty = [] if lines else {}
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(base) or not resolved.is_file():
                return empty
            stat = resolved.stat()
            if stat.st_size > MAX_BYTES:
                return empty
            signature = (stat.st_mtime_ns, stat.st_size)
            key = (str(resolved), lines)
            cached = self.cache.get(key)
            if cached and cached[0] == signature:
                return cached[1]
            raw = resolved.read_bytes()
            if len(raw) > MAX_BYTES:
                return empty
            if lines:
                value = []
                # A writer may be halfway through its final JSONL record.
                for line in raw.splitlines(keepends=True):
                    if not line.endswith(b"\n"):
                        continue
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            value.append(item)
                    except (ValueError, UnicodeError):
                        continue
            else:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    return empty
            if len(self.cache) > 1024:
                self.cache.clear()
            self.cache[key] = (signature, value)
            return value
        except (OSError, ValueError, RuntimeError):
            return empty

    def campaign(self, campaign_id, now=None):
        if not NAME.fullmatch(campaign_id):
            raise FileNotFoundError
        directory = (self.root / campaign_id).resolve()
        if not directory.is_relative_to(self.root):
            raise FileNotFoundError
        manifest = self.read(directory, directory / "campaign.json")
        if not isinstance(manifest.get("trials"), list):
            raise FileNotFoundError
        now = now if now is not None else time.time_ns() // 1_000_000
        events = self.read(directory, directory / "events.jsonl", lines=True)
        result = self.read(directory, directory / "results.json")
        starts = {
            e["run_id"]: number(e.get("unix_ms"))
            for e in events
            if e.get("type") == "trial_started" and isinstance(e.get("run_id"), str)
        }
        records = {
            e["result"]["run_id"]: e["result"]
            for e in events
            if e.get("type") == "trial_finished"
            and isinstance(e.get("result"), dict)
            and isinstance(e["result"].get("run_id"), str)
        }
        finishes = {
            e["result"]["run_id"]: number(e.get("unix_ms"))
            for e in events
            if e.get("type") == "trial_finished"
            and isinstance(e.get("result"), dict)
            and isinstance(e["result"].get("run_id"), str)
        }
        records.update(
            {
                r["run_id"]: r
                for r in objects(result.get("trials"))
                if isinstance(r.get("run_id"), str)
            }
        )
        first = next(
            (
                number(e.get("unix_ms"))
                for e in events
                if e.get("type") == "campaign_started"
            ),
            None,
        )
        final = next(
            (e for e in reversed(events) if e.get("type") == "campaign_finished"), {}
        )
        finished = number(final.get("unix_ms"))
        terminal = bool(final or result)
        cancelled = result.get("cancelled") is True or final.get("cancelled") is True
        timing = self.read(
            self.timing_root, self.timing_root / campaign_id / "audit" / "timing.json"
        )
        audit = (
            {
                r["run_id"]: r
                for r in objects(timing.get("runs"))
                if isinstance(r.get("run_id"), str)
            }
            if timing.get("campaign_id") == manifest.get("campaign_id")
            and isinstance(manifest.get("campaign_id"), str)
            else {}
        )
        trials = []
        for entry in objects(manifest["trials"]):
            run_id = entry.get("run_id")
            if not isinstance(run_id, str) or not NAME.fullmatch(run_id):
                continue
            record = records.get(run_id) or self.read(
                directory, directory / "trials" / run_id / "result.json"
            )
            runtime = self.read(
                directory,
                directory / "runs" / run_id / "runtime-events.jsonl",
                lines=True,
            )
            if manifest.get("sdk_runtime"):
                runtime = list(runtime)
                run_root = directory / "runs" / run_id
                session_paths = [
                    run_root / "session/session.jsonl",
                    *sorted(run_root.glob("increment-*/session/session.jsonl"))[:4],
                ]
                for path in session_paths:
                    runtime.extend(self.read(directory, path, lines=True))
                runtime = sorted(
                    runtime, key=lambda event: number(event.get("unix_ms")) or 0
                )
            worker_start = number(record.get("started_unix_ms")) or starts.get(run_id)
            trial_terminal = bool(record) or terminal
            trial_finish = number(record.get("finished_unix_ms")) or finishes.get(
                run_id
            )
            if (
                trial_finish is None
                and record
                and record.get("status") != "not_started"
            ):
                trial_finish = finished
            host_start = number(record.get("host_started_unix_ms"))
            host_end = number(record.get("host_finished_unix_ms"))
            elapsed_end = host_end or trial_finish or (None if trial_terminal else now)
            latest = (
                max(
                    [0, worker_start or 0, trial_finish or 0]
                    + [number(e.get("unix_ms")) or 0 for e in runtime]
                )
                or None
            )
            if record.get("status") == "not_started" or (
                cancelled and not record and not worker_start
            ):
                status = "cancelled"
            elif record:
                passed = (
                    record.get("task_success") is True
                    and record.get("host_exit_code") == 0
                    and record.get("evaluation_exit_code") == 0
                    and record.get("worker_exit_code", 0) == 0
                )
                status = "passed" if passed else "failed"
            elif worker_start or runtime:
                status = (
                    "in_progress" if latest and now - latest <= QUIET_MS else "quiet"
                )
            else:
                status = "queued"
            phases = []
            epochs = {}
            for event in runtime:
                stamp = number(event.get("unix_ms"))
                epoch = event.get("epoch")
                if event.get("type") == "phase_started" and type(epoch) is int:
                    phase = {
                        "name": label(event.get("phase")),
                        "status": "shutdown_unknown"
                        if trial_terminal
                        else ("quiet" if status == "quiet" else "in_progress"),
                        "elapsed_ms": duration(stamp, elapsed_end),
                        "started_at": stamp,
                    }
                    phases.append(phase)
                    epochs[epoch] = phase
                elif (
                    event.get("type") == "phase_stopped"
                    and type(epoch) is int
                    and epoch in epochs
                ):
                    phase = epochs[epoch]
                    phase.update(
                        status="stopped",
                        elapsed_ms=duration(phase["started_at"], stamp),
                    )
            current_phase = (
                phases[-1]["name"] if phases else ("setup" if worker_start else None)
            )
            if (
                phases
                and phases[-1]["status"] == "stopped"
                and status in ("in_progress", "quiet")
            ):
                current_phase = "evaluation"
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            workflow = (
                record.get("workflow_result")
                if isinstance(record.get("workflow_result"), dict)
                else {}
            )
            if manifest.get("sdk_runtime") and runtime:
                last_session = next(
                    (
                        event
                        for event in reversed(runtime)
                        if event.get("type") in ("session_started", "session_stopped")
                    ),
                    {},
                )
                current_phase = (
                    "evaluation"
                    if last_session.get("type") == "session_stopped"
                    else "workflow"
                )
            trials.append(
                {
                    **{
                        key: label(entry.get(key))
                        for key in ("fixture", "workflow", "family", "language", "size")
                    },
                    "run_id": run_id,
                    "repetition": number(entry.get("repetition")),
                    "status": status,
                    "task_success": boolean(record.get("task_success")),
                    "workflow_status": label(workflow.get("workflow_status")),
                    "stop_status": label(workflow.get("stop_status")),
                    "evaluation_status": label(workflow.get("evaluation_status")),
                    "phase": current_phase,
                    "phases": phases,
                    "started_at": worker_start,
                    "finished_at": trial_finish,
                    "latest_event_at": latest,
                    "elapsed_ms": duration(host_start or worker_start, elapsed_end),
                    "elapsed_basis": "host" if host_start else "worker",
                    "queue_wait_ms": number(
                        audit.get(run_id, {}).get("queue_wait_union_ms")
                    ),
                    "public_test_success": boolean(record.get("public_test_success")),
                    "hidden_test_success": boolean(record.get("hidden_test_success")),
                    "failure_classification": record["failure_classification"]
                    if record.get("failure_classification")
                    in ("scope_blocked", "runtime_failed")
                    else (
                        "worker_failed"
                        if status == "failed" and record.get("status") == "failed"
                        else None
                    ),
                    "usage": {
                        key: number(usage.get(key))
                        for key in (
                            "input_tokens",
                            "output_tokens",
                            "cached_input_tokens",
                        )
                    },
                }
            )
        updated = max(
            [0, first or 0, finished or 0] + [t["latest_event_at"] or 0 for t in trials]
        )
        if not updated:
            updated = int((directory / "campaign.json").stat().st_mtime * 1000)
        if terminal:
            state = "cancelled" if cancelled else "finished"
        elif first is None and not events:
            state = "prepared"
        else:
            state = "in_progress" if now - updated <= QUIET_MS else "quiet"
        counts = {
            key: sum(t["status"] == key for t in trials)
            for key in ("passed", "failed", "cancelled")
        }
        return {
            "id": campaign_id,
            "label": campaign_id,
            "state": state,
            "total": len(trials),
            "completed": sum(counts.values()),
            **counts,
            "accepted": sum(trial["task_success"] is True for trial in trials),
            "rejected": sum(trial["task_success"] is False for trial in trials),
            "acceptance_unknown": sum(
                trial["task_success"] is None for trial in trials
            ),
            "active": sum(t["status"] in ("in_progress", "quiet") for t in trials),
            "jobs": number(manifest.get("jobs")),
            "updated_at": updated,
            "started_at": first,
            "finished_at": finished,
            "elapsed_ms": duration(
                first,
                finished
                or (
                    (max([t["finished_at"] or 0 for t in trials], default=0) or None)
                    if terminal
                    else now
                ),
            ),
            "measurement_purpose": label(manifest.get("measurement_purpose")),
            "model": label(manifest.get("requested_model")),
            "phase_timeout_clock": label(manifest.get("phase_timeout_clock")),
            "trials": trials,
        }

    def list_campaigns(self):
        campaigns = []
        try:
            directories = list(self.root.iterdir())
        except FileNotFoundError:
            return campaigns
        for directory in directories:
            try:
                campaign = self.campaign(directory.name)
                campaigns.append(
                    {key: value for key, value in campaign.items() if key != "trials"}
                )
            except (FileNotFoundError, OSError):
                continue
        return sorted(
            campaigns, key=lambda campaign: campaign["updated_at"], reverse=True
        )


def make_server(store, port=8787):
    static_root = Path(__file__).resolve().parent

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if self.headers.get("Host", "").split(":")[0] not in (
                "127.0.0.1",
                "localhost",
            ):
                self.send_error(403)
                return
            path = unquote(urlsplit(self.path).path)
            try:
                if path in STATIC:
                    name, content_type = STATIC[path]
                    source = (static_root / name).resolve()
                    if not source.is_relative_to(static_root):
                        raise FileNotFoundError
                    payload = source.read_bytes()
                else:
                    with store.lock:
                        if path == "/api/campaigns":
                            data = {
                                "campaigns": store.list_campaigns(),
                                "observed_at": time.time_ns() // 1_000_000,
                            }
                        elif path.startswith("/api/campaigns/"):
                            data = store.campaign(path.removeprefix("/api/campaigns/"))
                        else:
                            raise FileNotFoundError
                    payload = json.dumps(data, ensure_ascii=True).encode()
                    content_type = "application/json"
            except FileNotFoundError:
                self.send_error(404)
                return
            except OSError:
                self.send_error(503, "Campaign data is unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign-root", type=Path, default=Path.home() / ".cache/codex-lab-campaigns"
    )
    parser.add_argument(
        "--timing-root", type=Path, default=Path.home() / ".cache/codex-lab-timing"
    )
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    with make_server(
        CampaignStore(args.campaign_root, args.timing_root), args.port
    ) as server:
        print(
            f"Read-only harness dashboard: http://127.0.0.1:{server.server_port}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
