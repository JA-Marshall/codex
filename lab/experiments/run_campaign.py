"""Run a finite unattended campaign from frozen inputs, retaining every trial."""

import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from campaign_inputs import (
    FIXTURE_NAMES,
    digest,
    freeze,
    load_campaign,
    read_json,
    validate_pins,
    write_json,
)
from campaign_service import check_service


def run_logged(command, prefix):
    """Drain subprocess pipes to bounded logs; never abandon a live child."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
        creationflags=0x08000200 if os.name == "nt" else 0,
    )
    errors = []

    def capture(pipe, suffix, limit):
        retained = 0
        try:
            with Path(str(prefix) + suffix).open("xb") as log:
                while chunk := pipe.read(65536):
                    log.write(chunk[: max(0, limit - retained)])
                    retained += len(chunk)
        except OSError as error:
            errors.append(str(error))
            while pipe.read(65536):
                pass
        finally:
            pipe.close()

    readers = [
        threading.Thread(
            target=capture, args=(process.stdout, ".stdout.log", 8 * 1024 * 1024)
        ),
        threading.Thread(
            target=capture, args=(process.stderr, ".stderr.log", 1024 * 1024)
        ),
    ]
    for reader in readers:
        reader.start()
    try:
        returncode = process.wait()
    finally:
        process.wait()
        for reader in readers:
            reader.join()
    if errors:
        raise OSError("subprocess log capture failed: " + errors[0])
    return returncode


def setup_trial(destination, fixture_name, task_root=None, toolchain=None, task_just=None):
    if task_root is not None:
        from task_registry import discover, setup

        tasks = discover(task_root)
        if fixture_name in tasks:
            task = tasks[fixture_name]
            return setup(destination, task,
                         toolchain if task.manifest["language"] == "rust" else None,
                         task_just if task.manifest["language"] == "rust" else None)
    if fixture_name == "durable-queue-v1":
        from queue_fixture import setup

        return setup(destination)
    from setup_fixture import setup

    return setup(destination, fixture_name)


def trial_commands(manifest, entry, metadata, directory):
    repository = Path(metadata["repository"])
    host = [
        manifest["binary"],
        "run",
        "--repository",
        str(repository),
        "--commit",
        metadata["commit"],
        "--codex-home",
        manifest["codex_home"],
        "--runs-directory",
        str(Path(manifest["output"]) / "runs"),
        "--run-id",
        entry["run_id"],
        "--task-file",
        str(repository / "TASK.md"),
        "--workflow-catalog",
        manifest["catalog"],
        "--instruction-root",
        manifest["archive"],
        "--workflow",
        entry["workflow"],
        "--campaign-policy",
        str(directory / "policy.json"),
    ]
    evaluator = "evaluate_task.py" if metadata.get("kind") == "repository_task" else (
        "evaluate_queue.py"
        if entry["fixture"] == "durable-queue-v1"
        else "evaluate_fixture.py"
    )
    evaluate = [
        manifest["python"],
        str(Path(manifest["archive"]) / "experiments" / evaluator),
        "--repository",
        str(repository),
        "--sandbox",
        manifest["sandbox"],
        "--output",
        str(directory / "evaluation"),
        "--fixture-manifest",
        str(directory / "fixture/fixture.json"),
        "--run",
        str(Path(manifest["output"]) / "runs" / entry["run_id"]),
    ]
    if metadata.get("language") == "rust":
        evaluate.extend(["--toolchain", manifest["task_toolchain"]])
    return host, evaluate


def usage(run):
    totals = dict.fromkeys(("input_tokens", "output_tokens", "cached_input_tokens"), 0)
    phases = sorted((run / "evidence").glob("phase-*.json"))
    if not phases or len(phases) > 32:
        return dict.fromkeys(totals)
    for phase in phases:
        current = (read_json(phase).get("token_usage") or {}).get(
            "total_token_usage", {}
        )
        for name, value in totals.items():
            amount = current.get(name)
            totals[name] = (
                value + amount
                if value is not None and type(amount) is int and amount >= 0
                else None
            )
    return totals


def run_trial(manifest, entry):
    directory = Path(manifest["output"]) / "trials" / entry["run_id"]
    # A direct worker invocation must not overwrite a previous attempt either.
    with (directory / "started.json").open("x", encoding="utf-8") as receipt:
        json.dump(
            {"campaign_id": manifest["campaign_id"], "run_id": entry["run_id"]}, receipt
        )
    record = dict(
        entry,
        status="failed",
        host_exit_code=None,
        evaluation_exit_code=None,
        task_success=None,
        started_unix_ms=time.time_ns() // 1000000,
    )
    try:
        validate_pins(manifest)
        if manifest.get("task_root"):
            metadata = setup_trial(directory / "fixture", entry["fixture"], manifest["task_root"],
                                   manifest.get("task_toolchain"), manifest.get("task_just"))
        else:
            metadata = setup_trial(directory / "fixture", entry["fixture"])
        repository = Path(metadata["repository"])
        policy = {
            "schema_version": 1,
            "campaign_id": manifest["campaign_id"],
            "run_id": entry["run_id"],
            "repository": str(repository),
            "repository_commit": metadata["commit"],
            "task_sha256": digest(repository / "TASK.md"),
            "workflow": entry["workflow"],
            "workflow_catalog_sha256": digest(manifest["catalog"]),
            "max_amendments": manifest["max_amendments"],
        }
        if metadata.get("kind") == "repository_task":
            policy["task_scope"] = {
                "schema_version": 1,
                "write_paths": metadata["write_paths"],
                "deny_read_paths": [manifest["task_root"]],
                "read_paths": [str(Path(sys.base_prefix).resolve())]
                + ([manifest["task_toolchain"], str(Path(manifest["task_just"]).parent)]
                   if metadata["language"] == "rust" else []),
            }
        write_json(directory / "policy.json", policy)
        record.update(
            repository=str(repository),
            repository_commit=metadata["commit"],
            policy_sha256=digest(directory / "policy.json"),
        )
        host, evaluate = trial_commands(manifest, entry, metadata, directory)
        validate_pins(manifest)
        check_service(manifest)
        record["host_exit_code"] = run_logged(host, directory / "host")
        if record["host_exit_code"] != 0:
            failure = Path(manifest["output"]) / "runs" / entry["run_id"] / "evidence/failure.json"
            if failure.is_file():
                classification = read_json(failure).get("classification")
                if classification in ("scope_blocked", "runtime_failed"):
                    record["failure_classification"] = classification
        # The evaluator owns terminal/shutdown checks, including failed hosts.
        validate_pins(manifest)
        record["evaluation_exit_code"] = run_logged(evaluate, directory / "evaluator")
        if record["evaluation_exit_code"] == 0:
            result = read_json(directory / "evaluation/evaluation.json")
            record.update(
                task_success=result["task_success"],
                public_test_success=result["public_test_success"],
                hidden_test_success=result["hidden_test_success"],
                status="finished",
            )
    except Exception as error:
        record["error"] = str(error)
    try:
        record["usage"] = usage(Path(manifest["output"]) / "runs" / entry["run_id"])
    except (OSError, ValueError, TypeError, KeyError) as error:
        record["usage"] = None
        record["usage_error"] = str(error)
    record["finished_unix_ms"] = time.time_ns() // 1000000
    write_json(directory / "result.json", record)
    return record


def worker_command(manifest, entry):
    return [
        manifest["python"],
        str(Path(manifest["archive"]) / "experiments/run_campaign.py"),
        "--trial",
        str(Path(manifest["output"]) / "campaign.json"),
        "--run-id",
        entry["run_id"],
        "--manifest-sha256",
        manifest["manifest_sha256"],
    ]


def coordinate(manifest, cancelled=None):
    cancelled = cancelled or threading.Event()
    output = Path(manifest["output"])
    validate_pins(manifest)
    check_service(manifest)
    # Exclusive creation deliberately refuses resume and any reuse of prior authority.
    with (output / "events.jsonl").open("x", encoding="utf-8") as journal:
        for name in ("trials", "runs"):
            (output / name).mkdir(exist_ok=False)
        pending, records, active = deque(manifest["trials"]), {}, {}
        sequence = 0

        def event(kind, **fields):
            nonlocal sequence
            sequence += 1
            journal.write(
                json.dumps(
                    dict(
                        schema_version=1,
                        sequence=sequence,
                        type=kind,
                        unix_ms=time.time_ns() // 1000000,
                        **fields,
                    )
                )
                + "\n"
            )
            journal.flush()

        def execute(entry):
            directory = output / "trials" / entry["run_id"]
            try:
                code = run_logged(worker_command(manifest, entry), directory / "worker")
                record = read_json(directory / "result.json")
                if record.get("run_id") != entry["run_id"]:
                    raise ValueError("foreign trial result")
                record["worker_exit_code"] = code
                return record
            except Exception as error:
                return dict(
                    entry,
                    status="failed",
                    error=str(error),
                    task_success=None,
                    host_exit_code=None,
                    evaluation_exit_code=None,
                )

        event(
            "campaign_started",
            campaign_id=manifest["campaign_id"],
            queued=len(pending),
            jobs=manifest["jobs"],
            automatic_retries=0,
            resume_supported=False,
        )
        with ThreadPoolExecutor(max_workers=manifest["jobs"]) as pool:
            while pending or active:
                while (
                    pending
                    and len(active) < manifest["jobs"]
                    and not cancelled.is_set()
                ):
                    entry = pending.popleft()
                    (output / "trials" / entry["run_id"]).mkdir(exist_ok=False)
                    event(
                        "trial_started",
                        run_id=entry["run_id"],
                        active_jobs=len(active) + 1,
                    )
                    active[pool.submit(execute, entry)] = entry
                if not active:
                    break
                finished, _ = wait(active, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in finished:
                    entry = active.pop(future)
                    record = future.result()
                    records[entry["run_id"]] = record
                    event("trial_finished", result=record, active_jobs=len(active))
                    print(
                        json.dumps(
                            {
                                "run_id": entry["run_id"],
                                "status": record["status"],
                                "task_success": record.get("task_success"),
                            }
                        ),
                        flush=True,
                    )
        for entry in pending:
            records[entry["run_id"]] = dict(
                entry, status="not_started", reason="campaign cancelled"
            )
        ordered = [records[entry["run_id"]] for entry in manifest["trials"]]
        succeeded = sum(
            record.get("task_success") is True
            and record.get("host_exit_code") == 0
            and record.get("evaluation_exit_code") == 0
            and record.get("worker_exit_code") == 0
            for record in ordered
        )
        totals = {}
        for name in ("input_tokens", "output_tokens", "cached_input_tokens"):
            values = [
                (record.get("usage") or {}).get(name)
                for record in ordered
                if record["status"] != "not_started"
            ]
            totals[name] = {
                "known_total": sum(value for value in values if type(value) is int),
                "unknown_trials": sum(value is None for value in values),
            }
        result = dict(
            schema_version=1,
            campaign_id=manifest["campaign_id"],
            cancelled=cancelled.is_set(),
            total=len(ordered),
            passed=succeeded,
            failed=len(ordered) - succeeded,
            workflow_completed=sum(
                record.get("host_exit_code") == 0 for record in ordered
            ),
            task_passed=sum(record.get("task_success") is True for record in ordered),
            task_failed=sum(record.get("task_success") is False for record in ordered),
            scope_blocked=sum(record.get("failure_classification") == "scope_blocked" for record in ordered),
            evaluation_failures=sum(
                record.get("evaluation_exit_code") not in (None, 0)
                for record in ordered
            ),
            evaluation_unknown=sum(
                record.get("task_success") is None for record in ordered
            ),
            not_started=len(pending),
            usage=totals,
            trials=ordered,
            resume_supported=False,
        )
        write_json(output / "results.json", result)
        event(
            "campaign_finished",
            passed=succeeded,
            total=len(ordered),
            cancelled=cancelled.is_set(),
        )
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        type=Path,
        help="Execute a previously frozen, never-started manifest",
    )
    parser.add_argument("--trial", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-id", help=argparse.SUPPRESS)
    parser.add_argument("--manifest-sha256", help=argparse.SUPPRESS)
    for name in (
        "binary",
        "codex-home",
        "catalog",
        "instruction-root",
        "sandbox",
        "output",
    ):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--workflow", action="append")
    parser.add_argument("--fixture", action="append")
    parser.add_argument("--task-root", type=Path, help="Versioned repository task library")
    parser.add_argument("--task-split", choices=("development", "study", "confirmation"),
                        help="Select every repository task in this split instead of listing --fixture")
    parser.add_argument("--task-toolchain", type=Path, help="Pinned Rust toolchain directory")
    parser.add_argument("--task-just", type=Path, help="Existing just executable to freeze for Rust public test recipes")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--max-amendments", type=int, default=0, choices=range(5))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--provider-service", type=Path, help="Pinned shared Muse proxy service.json"
    )
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("campaign preparation and execution require Linux/Python 3.12")
    if args.trial:
        if not args.manifest_sha256 or not args.run_id:
            parser.error("trial workers require a pinned campaign and run ID")
        manifest = load_campaign(args.trial, args.manifest_sha256)
        entry = next(
            entry for entry in manifest["trials"] if entry["run_id"] == args.run_id
        )
        run_trial(manifest, entry)
        return 0
    if args.execute:
        manifest = load_campaign(args.execute, args.manifest_sha256)
        check_service(manifest)
        frozen_runner = Path(manifest["archive"]) / "experiments/run_campaign.py"
        if Path(__file__).resolve() != frozen_runner.resolve():
            os.execv(
                manifest["python"],
                [
                    manifest["python"],
                    str(frozen_runner),
                    "--execute",
                    str(args.execute.resolve()),
                    "--manifest-sha256",
                    manifest["manifest_sha256"],
                ],
            )
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        result = coordinate(manifest, stop)
        print(
            json.dumps(
                {
                    "results": str(Path(manifest["output"]) / "results.json"),
                    "passed": result["passed"],
                    "total": result["total"],
                }
            )
        )
        return int(result["failed"] != 0 or result["cancelled"])
    if args.task_split:
        if args.fixture or not args.task_root:
            parser.error("--task-split requires --task-root and cannot be combined with --fixture")
        from task_registry import discover

        args.fixture = sorted(task.name for task in discover(args.task_root).values()
                              if task.manifest["split"] == args.task_split)
        if not args.fixture:
            parser.error("the selected task split is empty")
    required = (
        "binary",
        "codex_home",
        "catalog",
        "instruction_root",
        "sandbox",
        "output",
        "workflow",
        "fixture",
    )
    if any(getattr(args, name) is None for name in required):
        parser.error(
            "freezing requires --binary, --codex-home, --catalog, --instruction-root, --sandbox, --output, --workflow and --fixture"
        )
    manifest = freeze(args)
    command = [
        manifest["python"],
        str(Path(manifest["archive"]) / "experiments/run_campaign.py"),
        "--execute",
        str(Path(manifest["output"]) / "campaign.json"),
    ]
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "campaign": str(Path(manifest["output"]) / "campaign.json"),
                    "trials": len(manifest["trials"]),
                    "model_calls": 0,
                    "execute": command,
                },
                indent=2,
            )
        )
        return 0
    os.execv(command[0], command)


if __name__ == "__main__":
    raise SystemExit(main())
