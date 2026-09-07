"""Run isolated prepared hosts concurrently, routing live exact human decisions."""

import argparse
from collections import deque
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time

from batch_inputs import fingerprint, load_batch

MAX_FRAME = 4 * 1024 * 1024
MAX_LOG = 8 * 1024 * 1024


def collect_output(process, name, directory, inbox):
    def stderr():
        size = 0
        try:
            with (directory / "stderr.log").open("xb") as log:
                while data := process.stderr.read(65536):
                    log.write(data[: max(0, 1024 * 1024 - size)])
                    size += len(data)
        except OSError:
            inbox.put((name, "error", "stderr capture failed"))
            while process.stderr.read(65536):
                pass

    error_reader = threading.Thread(target=stderr, daemon=True)
    error_reader.start()
    size = 0
    try:
        with (directory / "stdout.log").open("xb") as log:
            while line := process.stdout.readline(MAX_FRAME + 1):
                log.write(line[: max(0, MAX_LOG - size)])
                size += len(line)
                if len(line) > MAX_FRAME or size > MAX_LOG:
                    if size - len(line) <= MAX_LOG:
                        inbox.put((name, "error", "child output exceeds bounds"))
                    continue
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    continue  # The ordinary final CLI result is pretty-printed JSON.
                if isinstance(value, dict) and value.get("type") == "lab_review":
                    inbox.put((name, "review", value))
    except OSError:
        inbox.put((name, "error", "stdout capture failed"))
        while process.stdout.read(65536):
            pass
    process.wait()
    error_reader.join()
    process.stdout.close()
    process.stderr.close()
    inbox.put((name, "exit", process.returncode))


def collect_input(source, inbox):
    for _ in range(4096):
        line = source.readline(16385)
        if not line:
            break
        if len(line) > 16384 or not line.endswith("\n"):
            inbox.put((None, "error", "human input exceeds bounds or is partial"))
            break
        inbox.put((None, "input", line.strip()))
    else:
        inbox.put((None, "error", "human command limit reached; closing input"))
    inbox.put((None, "eof", None))


class Batch:
    def __init__(self, config, output, source=sys.stdin):
        self.config, self.output, self.source = config, output, source
        self.inbox = queue.Queue(maxsize=64)
        self.children, self.waiting = {}, deque()
        self.draining, self.failed = False, False
        self.cancel_requested = False
        self.started = time.monotonic()

    def event(self, kind, **fields):
        value = {
            "schema_version": 1,
            "sequence": self.sequence,
            "type": kind,
            "unix_ms": time.time_ns() // 1000000,
            "elapsed_ms": int((time.monotonic() - self.started) * 1000),
            **fields,
        }
        self.sequence += 1
        self.trace.write(json.dumps(value) + "\n")
        self.trace.flush()

    def review(self, name, value):
        child = self.children[name]
        if child["broken"]:
            return
        target, rendered = value["target"], value["rendered"]
        if (
            value["schema_version"] != 1
            or type(value["request_id"]) is not int
            or value["request_id"] != child["sequence"] + 1
            or value["request_id"] > 32
            or child["request"] is not None
            or target["run_id"] != name
            or not isinstance(rendered["content"], str)
            or len(rendered["content"].encode()) > 512 * 1024
        ):
            raise ValueError("invalid or stale child review request")
        # Only the trusted JsonReviewer emits this frame, after phase shutdown.
        child.update(active=False, sequence=value["request_id"], request=value)
        request_file = self.output / name / f"review-{value['request_id']:02}.json"
        with request_file.open("x") as file:
            json.dump(value, file, indent=2)
        self.event(
            "review_requested",
            run_id=name,
            request_id=value["request_id"],
            target=target,
            review=str(request_file),
        )
        print(
            f"REVIEW {name} {value['request_id']} {json.dumps(target)}\nPlan: {request_file}",
            flush=True,
        )
        if self.draining:
            child["process"].stdin.close()

    def decision(self, line):
        name, request_id, command = line.split(" ", 2)
        child = self.children[name]
        request = child["request"]
        if (
            self.draining
            or request is None
            or request["request_id"] != int(request_id)
            or child["queued"]
        ):
            raise ValueError("decision has no current unqueued review request")
        if command.startswith("approve "):
            if command != "approve " + request["target"]["content_sha256"]:
                raise ValueError("approval digest does not match current target")
        elif command != "abort" and not (
            command.startswith("reject ") or command.startswith("edit ")
        ):
            raise ValueError(
                "expected approve DIGEST, reject REASON, edit PATH, or abort"
            )
        if len(command.encode()) > 8192 or any(ord(c) < 32 for c in command):
            raise ValueError("invalid decision command")
        response = {
            "schema_version": 1,
            "request_id": request["request_id"],
            "target": request["target"],
            "command": command,
        }
        self.event("human_decision_queued", run_id=name, response=response)
        child["queued"] = True
        self.waiting.append((name, response))

    def dispatch(self):
        for _ in range(len(self.waiting)):
            name, response = self.waiting.popleft()
            child = self.children[name]
            if self.draining or child["exit"] is not None or child["broken"]:
                continue
            active = sum(c["active"] for c in self.children.values())
            if response["command"] != "abort" and active >= self.config["jobs"]:
                self.waiting.append((name, response))
                continue
            process = child["process"]
            try:
                process.stdin.write((json.dumps(response) + "\n").encode())
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.fail_child(name, "review channel closed")
                continue
            child.update(
                active=response["command"] != "abort", request=None, queued=False
            )
            self.event(
                "decision_sent",
                run_id=name,
                request_id=response["request_id"],
                active_jobs=sum(c["active"] for c in self.children.values()),
            )

    def fail_child(self, name, reason):
        self.failed = True
        child = self.children[name]
        child["broken"] = True
        child["process"].stdin.close()
        self.event("channel_failed", run_id=name, reason=reason)
        # Keep any execution slot until exit: unknown state is not quiescence.

    def drain(self):
        if not self.draining:
            self.draining = True
            self.failed |= self.cancel_requested
            self.event("input_closed", queued_decisions_discarded=len(self.waiting))
            self.waiting.clear()
            for child in self.children.values():
                child["process"].stdin.close()
            print(
                "Input closed: no further decisions; waiting for existing hosts to exit.",
                flush=True,
            )

    def run(self):
        try:
            return self.coordinate()
        finally:
            # Even a coordinator/logging exception must not abandon live hosts.
            # Close review channels, drain their pipes, and await natural exit.
            for child in self.children.values():
                child["process"].stdin.close()
            while any(c["process"].poll() is None for c in self.children.values()):
                try:
                    self.inbox.get(timeout=0.2)
                except queue.Empty:
                    pass

    def coordinate(self):
        self.output.mkdir(exist_ok=False)
        (self.output / "batch.json").write_text(
            json.dumps(self.config, indent=2) + "\n"
        )
        self.sequence = 1
        with (self.output / "events.jsonl").open("x") as self.trace:
            self.event(
                "batch_started",
                jobs=self.config["jobs"],
                max_hosts=32,
                cpu_count=os.cpu_count(),
                platform=sys.platform,
                python=sys.version,
                automatic_retries=0,
                authority_restored=False,
            )
            for entry in self.config["runs"]:
                if self.cancel_requested:
                    self.drain()
                    break
                name = entry["run_id"]
                try:
                    if fingerprint(Path(entry["prepared"])) != entry["prepared_sha256"]:
                        raise ValueError("prepared descriptor changed before launch")
                    if (
                        fingerprint(Path(self.config["binary"]))
                        != self.config["binary_sha256"]
                    ):
                        raise ValueError("batch binary changed before launch")
                    directory = self.output / name
                    directory.mkdir()
                    process = subprocess.Popen(
                        [
                            self.config["binary"],
                            "run-prepared",
                            "--prepared",
                            entry["prepared"],
                            "--run-id",
                            name,
                            "--review-json",
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=os.name != "nt",
                        creationflags=0x08000200 if os.name == "nt" else 0,
                    )
                    self.children[name] = {
                        "process": process,
                        "active": False,
                        "sequence": 0,
                        "request": None,
                        "queued": False,
                        "exit": None,
                        "broken": False,
                    }
                    self.event(
                        "host_started",
                        run_id=name,
                        pid=process.pid,
                        artifacts=entry["artifacts"],
                    )
                    threading.Thread(
                        target=collect_output,
                        args=(process, name, directory, self.inbox),
                        daemon=True,
                    ).start()
                except (OSError, ValueError) as error:
                    self.failed = True
                    self.event("launch_failed", run_id=name, reason=str(error))
            threading.Thread(
                target=collect_input, args=(self.source, self.inbox), daemon=True
            ).start()
            while any(c["exit"] is None for c in self.children.values()):
                try:
                    if self.cancel_requested:
                        self.drain()
                    name, kind, value = self.inbox.get(timeout=0.2)
                    if kind == "review":
                        try:
                            self.review(name, value)
                        except (KeyError, TypeError, ValueError) as error:
                            self.fail_child(name, str(error))
                    elif kind == "input":
                        try:
                            self.decision(value)
                        except (KeyError, TypeError, ValueError) as error:
                            print("Decision refused: " + str(error), flush=True)
                            self.event("decision_refused", reason=str(error))
                    elif kind == "exit":
                        self.children[name].update(
                            exit=value, active=False, request=None
                        )
                        self.children[name]["process"].stdin.close()
                        self.failed |= value != 0
                        self.event("host_exited", run_id=name, exit_code=value)
                        print(f"EXIT {name} {value}", flush=True)
                    elif kind == "eof":
                        self.drain()
                    elif name is not None:
                        self.fail_child(name, value)
                    else:
                        print(value, flush=True)
                    self.dispatch()
                except queue.Empty:
                    continue
                except KeyboardInterrupt:
                    self.cancel_requested = True
                    self.drain()
            result = {
                "schema_version": 1,
                "failed": self.failed,
                "exit_codes": {
                    e["run_id"]: self.children.get(e["run_id"], {}).get("exit")
                    for e in self.config["runs"]
                },
                "note": "Process exits are not task success or proof of tool shutdown; use the existing evaluator.",
            }
            (self.output / "result.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            self.event("batch_exited", failed=self.failed)
        return 1 if self.failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    config = load_batch(args.manifest, args.output, args.jobs)
    print(
        "Decisions: RUN_ID REQUEST_ID approve DIGEST | reject REASON | edit PATH | abort",
        flush=True,
    )
    batch = Batch(config, args.output.resolve())
    # Defer Ctrl+C into the coordinator, including while Popen is starting a host.
    signal.signal(signal.SIGINT, lambda *_: setattr(batch, "cancel_requested", True))
    raise SystemExit(batch.run())
