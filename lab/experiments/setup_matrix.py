"""Freeze and prepare the bounded queue instruction matrix, without execution authority."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

from queue_fixture import setup
from setup_fixture import git, sha256
from setup_suite import validate_pins


def conditions():
    combinations = list(itertools.product("ab", repeat=3))
    result = []
    for block in range(4):
        rotated = combinations[block:] + combinations[:block]
        for planner, executor, verifier in rotated:
            name = f"queue-r{block + 1}-{planner}{executor}{verifier}"
            result.append({"id": name, "block": block + 1,
                "planner": planner, "executor": executor, "verifier": verifier,
                "workflow": f"queue-{planner}{executor}{verifier}-v1",
                "parent": None if executor == verifier == "a" else f"queue-r{block + 1}-{planner}aa",
                "preparation_id": name + "-prepared", "execution_id": name + "-execution"})
    return result


def freeze(destination, binary, codex_home):
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        raise ValueError("matrix requires Linux/Python 3.12")
    source = Path(__file__).resolve().parents[2]
    if git(source, "status", "--porcelain"):
        raise ValueError("commit source changes before freezing a campaign")
    binary, codex_home = binary.resolve(strict=True), codex_home.resolve(strict=True)
    config_file = codex_home / "config.toml"
    config = tomllib.loads(config_file.read_text())
    model_catalog = Path(config["model_catalog_json"])
    if not model_catalog.is_absolute():
        model_catalog = codex_home / model_catalog
    destination = destination.resolve()
    destination.mkdir(exist_ok=False)
    archive = destination / "inputs/lab"
    archive.mkdir(parents=True)
    for name in ("experiments", "fixtures", "workflows", "instructions"):
        shutil.copytree(source / "lab" / name, archive / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("runs", "tasks", "traces", "preparation"):
        (destination / name).mkdir()
    pins = [binary, binary.parent / "codex-resources/bwrap", config_file,
        model_catalog.resolve(strict=True), Path(sys.executable).resolve()]
    pins += [p for p in archive.rglob("*") if p.is_file()]
    entries = conditions()
    for entry in entries:
        parent = destination / "tasks" / entry["id"]
        metadata = setup(parent)
        entry.update(repository=metadata["repository"], commit=metadata["commit"],
            fixture_manifest=str(parent / "fixture.json"))
        pins.append(parent / "fixture.json")
    if len({entry["commit"] for entry in entries}) != 1:
        raise ValueError("matrix baselines differ")
    manifest = {"schema_version": 1, "source_commit": git(source, "rev-parse", "HEAD"),
        "binary": str(binary), "codex_home": str(codex_home), "archive": str(archive),
        "requested_model": config["model"], "conditions": entries,
        "limits": {"concurrency": 8, "aggregate_token_allocation": 35000000,
            "hard_cumulative_token_limit": None, "hard_spend_limit": None,
            "automatic_retries": 0, "automatic_amendment_approvals": 0,
            "model_context_window": config.get("model_context_window"),
            "model_auto_compact_token_limit": config.get("model_auto_compact_token_limit"),
            "existing_phase_seconds": 1800, "existing_phase_events": 10000,
            "existing_phase_event_bytes": 4194304, "existing_phase_threads": 32,
            "existing_fragment_bytes": 8192, "existing_combined_fragment_bytes": 16384},
        "pins": {str(p): sha256(p) for p in sorted(set(pins))},
        "approval": "Preparation only. Exact generated plans and execution targets require human approval.",
        "analysis": "Four paired blocks per planner; shared plans are not independent planner samples. Retain failures."}
    (destination / "matrix.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def prepare_one(root, manifest, entry, parent=None):
    validate_pins(manifest)
    repository = Path(entry["repository"])
    if git(repository, "rev-parse", "HEAD") != entry["commit"] or git(repository, "status", "--porcelain"):
        raise ValueError("task baseline changed: " + entry["id"])
    archive = Path(manifest["archive"])
    command = [manifest["binary"], "prepare", "--repository", str(repository),
        "--commit", entry["commit"], "--codex-home", manifest["codex_home"],
        "--runs-directory", str(root / "runs"), "--run-id", entry["preparation_id"],
        "--task-file", str(archive / "fixtures/durable-queue-v1/task.txt"),
        "--workflow-catalog", str(archive / "workflows/queue-matrix.toml"),
        "--instruction-root", str(archive), "--workflow", entry["workflow"]]
    if parent is not None:
        command += ["--plan-file", str(root / "runs" / parent["preparation_id"] / "plans/1/plan.json")]
    log = root / "preparation" / entry["id"]
    started = time.time_ns()
    with log.with_suffix(".stdout.log").open("xb") as stdout, log.with_suffix(".stderr.log").open("xb") as stderr:
        # A closed decision channel cannot approve any plan. Never record environment secrets.
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            cwd=root / "inputs", check=False)
    record = {"id": entry["id"], "started_ns": started, "finished_ns": time.time_ns(),
        "exit_code": result.returncode, "command": command, "status": "failed"}
    if result.returncode == 0:
        descriptor_path = root / "runs" / entry["preparation_id"] / "evidence/prepared.json"
        descriptor = json.loads(descriptor_path.read_text())
        if git(repository, "status", "--porcelain") or git(repository, "rev-parse", "HEAD") != entry["commit"]:
            raise ValueError("planning changed the baseline")
        if parent is not None:
            prior = json.loads((root / "runs" / parent["preparation_id"] / "evidence/prepared.json").read_text())
            if descriptor["plan_sha256"] != prior["plan_sha256"]:
                raise ValueError("import changed canonical plan")
        record.update(status="awaiting_plan_approval", prepared=str(descriptor_path),
            prepared_sha256=sha256(descriptor_path), target={"run_id": entry["execution_id"],
                "plan_id": descriptor["plan_id"], "revision": descriptor["revision"],
                "content_sha256": descriptor["plan_sha256"], "run_spec_sha256": descriptor["run_spec_sha256"]})
    log.with_suffix(".result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def schedule(entries, worker, emit):
    """Run eight independent planners; admit each plan's clones as soon as it is ready."""
    results = {}
    by_id = {entry["id"]: entry for entry in entries}
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(worker, entry, None): entry for entry in entries if entry["parent"] is None}
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                entry = pending.pop(future)
                try:
                    record = future.result()
                except Exception as error:
                    record = {"id": entry["id"], "status": "failed", "error": str(error)}
                results[entry["id"]] = record
                emit(record)
                for child in entries:
                    if child["parent"] != entry["id"]:
                        continue
                    if record["status"] == "awaiting_plan_approval":
                        pending[pool.submit(worker, child, by_id[child["parent"]])] = child
                    else:
                        blocked = {"id": child["id"], "status": "blocked_by_failed_plan", "parent": entry["id"]}
                        results[child["id"]] = blocked
                        emit(blocked)
    return [results[entry["id"]] for entry in entries]


def prepare(root):
    root = root.resolve(strict=True)
    manifest = json.loads((root / "matrix.json").read_text())
    validate_pins(manifest)
    # Exclusive creation prevents accidental reruns, including after interruption.
    with (root / "preparation.jsonl").open("x") as trace:
        def emit(record):
            trace.write(json.dumps(record) + "\n")
            trace.flush()
            print(json.dumps({"id": record["id"], "status": record["status"]}), flush=True)
        results = schedule(manifest["conditions"], lambda entry, parent: prepare_one(root, manifest, entry, parent), emit)
    validate_pins(manifest)
    (root / "review.json").write_text(json.dumps({"status": "awaiting human review", "conditions": results}, indent=2) + "\n")
    batch = {"schema_version": 1, "binary": manifest["binary"],
        "binary_sha256": manifest["pins"][manifest["binary"]], "runs": [
            {"run_id": result["target"]["run_id"], "prepared": result["prepared"],
                "prepared_sha256": result["prepared_sha256"]}
            for result in results if result["status"] == "awaiting_plan_approval"]}
    (root / "batch-input.json").write_text(json.dumps(batch, indent=2) + "\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("setup")
    create.add_argument("destination", type=Path)
    create.add_argument("--binary", type=Path, required=True)
    create.add_argument("--codex-home", type=Path, required=True)
    planning = commands.add_parser("prepare")
    planning.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.command == "setup":
        result = freeze(args.destination, args.binary, args.codex_home)
        print(json.dumps({"conditions": len(result["conditions"]), "matrix": str(args.destination / "matrix.json")}))
    else:
        prepare(args.root)
