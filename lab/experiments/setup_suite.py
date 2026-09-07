"""Freeze three diagnostic pairs and prepare unapproved plans; never execute tasks."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

from fixture_registry import FIXTURES
from setup_fixture import git, setup, sha256


def setup_suite(destination: Path, binary: Path, codex_home: Path):
    source = Path(__file__).resolve().parents[2]
    binary, codex_home = binary.resolve(strict=True), codex_home.resolve(strict=True)
    config_file = codex_home / "config.toml"
    config = tomllib.loads(config_file.read_text())
    catalog = Path(config["model_catalog_json"])
    if not catalog.is_absolute():
        catalog = codex_home / catalog
    destination = destination.resolve()
    destination.mkdir(exist_ok=False)
    archive = destination / "inputs/lab"
    archive.mkdir(parents=True)
    for name in ("experiments", "fixtures", "workflows", "instructions"):
        shutil.copytree(source / "lab" / name, archive / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destination / "runs").mkdir()
    (destination / "tasks").mkdir()
    pins = [binary, binary.parent / "codex-resources/bwrap", config_file, catalog.resolve(strict=True), Path(sys.executable).resolve()]
    pins += [p for p in archive.rglob("*") if p.is_file()]
    tasks = []
    for index, name in enumerate(FIXTURES):
        parent = destination / "tasks" / name
        parent.mkdir()
        conditions = {}
        for short in ("md", "json"):
            metadata = setup(parent / short, name)
            run_id = name + "-" + short
            conditions[short] = {"fixture_manifest": str(parent / short / "fixture.json"),
                                 "repository": metadata["repository"], "commit": metadata["commit"],
                                 "preparation_id": run_id + "-prepared", "execution_id": run_id + "-execution"}
            pins.append(parent / short / "fixture.json")
        if conditions["md"]["commit"] != conditions["json"]["commit"]:
            raise ValueError("pair baseline differs")
        tasks.append({"fixture": name, "conditions": conditions, "execution_order": ["md", "json"] if index % 2 == 0 else ["json", "md"]})
    manifest = {"schema_version": 1, "source_commit": git(source, "rev-parse", "HEAD"),
                "source_dirty": bool(git(source, "status", "--porcelain")),
                "binary": str(binary), "codex_home": str(codex_home), "archive": str(archive),
                "requested_model": config["model"], "tasks": tasks,
                "limits": {"execution_attempts_per_condition": 1, "execution_attempts_total": 6,
                           "automatic_retries": 0, "automatic_amendment_approvals": 0,
                           "existing_host_max_phases": 32, "existing_host_max_phase_seconds": 1800,
                           "existing_host_max_phase_events": 10000, "existing_host_max_phase_event_bytes": 4194304,
                           "existing_context_fragment_bytes": 8192, "existing_combined_context_bytes": 16384,
                           "model_context_window": config.get("model_context_window"),
                           "model_auto_compact_token_limit": config.get("model_auto_compact_token_limit"),
                           "hard_cumulative_token_limit": None, "hard_spend_limit": None},
                "pins": {str(p): sha256(p) for p in sorted(set(pins))},
                "approval": "Each exact live task target requires a human decision; this manifest grants no authority.",
                "analysis": "One pair per task, report all failures; no statistical winner or immutable serving revision claim."}
    (destination / "suite.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate_pins(manifest):
    for name, expected in manifest["pins"].items():
        if sha256(Path(name)) != expected:
            raise ValueError("frozen suite input changed: " + name)


def prepare_task(root: Path, task_name: str):
    root = root.resolve(strict=True)
    manifest = json.loads((root / "suite.json").read_text())
    validate_pins(manifest)
    task = next(t for t in manifest["tasks"] if t["fixture"] == task_name)
    archive, runs = Path(manifest["archive"]), root / "runs"
    targets = []
    for short in ("md", "json"):
        condition = task["conditions"][short]
        run = runs / condition["preparation_id"]
        command = [manifest["binary"], "prepare", "--repository", condition["repository"],
                   "--commit", condition["commit"], "--codex-home", manifest["codex_home"],
                   "--runs-directory", str(runs), "--run-id", condition["preparation_id"],
                   "--task-file", str(archive / "fixtures" / task_name / "task.txt"),
                   "--workflow-catalog", str(archive / "workflows/foundation.toml"),
                   "--instruction-root", str(archive), "--workflow", "plan-" + short + "-v1"]
        if short == "json":
            command += ["--plan-file", str(runs / task["conditions"]["md"]["preparation_id"] / "plans/1/plan.json")]
        log = root / "tasks" / task_name / (short + "-prepare")
        print("Preparing " + condition["preparation_id"], flush=True)
        # Keys may be supplied in the calling environment; never print/persist them.
        # Closed stdin makes this planning-only coordinator unable to approve.
        with log.with_suffix(".stdout.log").open("xb") as stdout, log.with_suffix(".stderr.log").open("xb") as stderr:
            result = subprocess.run(command, cwd=archive.parents[1], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, check=False)
        log.with_suffix(".exit.json").write_text(json.dumps({"exit_code": result.returncode, "command": command}) + "\n")
        if result.returncode:
            raise RuntimeError("preparation failed; inspect " + str(log))
        descriptor = json.loads((run / "evidence/prepared.json").read_text())
        targets.append({"run_id": condition["execution_id"], "plan_id": descriptor["plan_id"],
                        "revision": descriptor["revision"], "content_sha256": descriptor["plan_sha256"],
                        "run_spec_sha256": descriptor["run_spec_sha256"]})
    if targets[0]["content_sha256"] != targets[1]["content_sha256"]:
        raise ValueError("canonical plans differ")
    validate_pins(manifest)
    for condition in task["conditions"].values():
        repository = Path(condition["repository"])
        if git(repository, "rev-parse", "HEAD") != condition["commit"] or git(repository, "status", "--porcelain"):
            raise ValueError("planning changed the task baseline")
    with (root / "tasks" / task_name / "review.json").open("x") as output:
        json.dump({"status": "awaiting separate human decisions", "targets": targets}, output, indent=2)
        output.write("\n")
    print(json.dumps({"fixture": task_name, "status": "awaiting_plan_approval", "targets": targets}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("setup")
    create.add_argument("destination", type=Path)
    create.add_argument("--binary", type=Path, required=True)
    create.add_argument("--codex-home", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("suite", type=Path)
    prepare.add_argument("--task", choices=FIXTURES, required=True)
    args = parser.parse_args()
    if args.command == "setup":
        manifest = setup_suite(args.destination, args.binary, args.codex_home)
        print(json.dumps({"suite": str(args.destination / "suite.json"), "tasks": len(manifest["tasks"])}))
    else:
        prepare_task(args.suite, args.task)
