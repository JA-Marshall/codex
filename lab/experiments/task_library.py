"""List coding tasks or calibrate their graders offline before model experiments."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

from evaluate_task import evaluate
from task_registry import discover, evaluator_fingerprint, inventory, setup, read_json
from corpus_manifest import fingerprint
from campaign_inputs import digest
from corpus_calibration import driver_fingerprint


def overlay(source, destination):
    for name in inventory(source):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)


def calibrate(tasks, output, sandbox, toolchain=None):
    output = Path(output).resolve()
    if any(
        output.is_relative_to(task.root) or task.root.is_relative_to(output)
        for task in tasks.values()
    ):
        raise ValueError("calibration output must not overlap task assets")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    task_inputs = {
        name: fingerprint(inventory(task.root)) for name, task in tasks.items()
    }
    evaluator_hashes = evaluator_fingerprint()
    driver_hashes = driver_fingerprint()
    for name, task in tasks.items():
        selected_toolchain = toolchain if task.manifest["language"] == "rust" else None
        root = output / name
        root.mkdir()
        alternatives = task.manifest.get("valid_alternatives", [])
        variants = ["baseline", "solution", *alternatives, *task.manifest["mutants"]]
        policy = None
        if task.manifest["schema_version"] == 2:
            policy = read_json(task.root / "private/policy.json")
            variants.insert(1, "irrelevant-patch")
        for variant in variants:
            directory = root / variant
            metadata = setup(directory, task, selected_toolchain)
            repository = Path(metadata["repository"])
            if variant == "irrelevant-patch":
                (repository / "tests/calibration-note.txt").write_text(
                    "An irrelevant note.\n"
                )
            behavior = None
            if policy is not None:
                from provider_proxy import Journal
                from task_v2 import AuthorizedOwner, TaskSpecV2

                journal = Journal(directory / "reference-owner.jsonl")
                spec = TaskSpecV2.load(task.root, task.manifest)
                owner = AuthorizedOwner(spec.owner_facts, journal)
                try:
                    if variant not in ("baseline", "irrelevant-patch"):
                        for question in policy.get("calibration_questions", []):
                            owner.ask(
                                {
                                    "questions": [
                                        {"id": "reference", "question": question}
                                    ]
                                }
                            )
                    behavior = {
                        "asked_facts": owner.snapshot()["asked_facts"],
                        "reached_milestones": [],
                    }
                finally:
                    journal.stream.close()
                if spec.changes:
                    from calibration_changes import calibrate_changes

                    behavior = calibrate_changes(
                        task,
                        directory,
                        repository,
                        sandbox,
                        selected_toolchain,
                        variant,
                        behavior,
                        overlay,
                    )
            if variant not in ("baseline", "irrelevant-patch"):
                overlay(task.root / "solution", repository)
            if variant in task.manifest["mutants"]:
                overlay(task.root / "mutants" / variant, repository)
            elif variant in alternatives:
                overlay(task.root / "alternatives" / variant, repository)
            result = evaluate(
                repository,
                sandbox,
                directory / "evaluation",
                directory / "fixture.json",
                toolchain=selected_toolchain,
                behavior=behavior,
            )
            expected = variant == "solution" or variant in alternatives
            record = {
                "task": name,
                "variant": variant,
                "expected_pass": expected,
                "actual_pass": result["task_success"],
                "calibrated": result["task_success"] is expected,
                "evaluation": str(directory / "evaluation/evaluation.json"),
                "evaluation_sha256": digest(directory / "evaluation/evaluation.json"),
            }
            if policy is not None:
                intended = policy.get("mutant_failures", {}).get(variant, [])
                record.update(
                    behavior_source="offline scripted reference owner",
                    intended_failures=intended,
                    intended_failures_observed=all(
                        result["requirement_coverage"].get(key) is False
                        for key in intended
                    ),
                )
                record["calibrated"] &= record["intended_failures_observed"]
            records.append(record)
            print(json.dumps(record), flush=True)
    result = {
        "schema_version": 1,
        "tasks": len(tasks),
        "variants": len(records),
        "calibrated": all(record["calibrated"] for record in records),
        "model_calls": 0,
        "records": records,
        "task_inputs": task_inputs,
        "evaluator_sha256": evaluator_hashes,
        "calibration_driver_sha256": driver_hashes,
    }
    if task_inputs != {
        name: fingerprint(inventory(task.root)) for name, task in tasks.items()
    }:
        raise ValueError("task assets changed during calibration")
    if evaluator_hashes != evaluator_fingerprint():
        raise ValueError("evaluator changed during calibration")
    if driver_hashes != driver_fingerprint():
        raise ValueError("calibration driver changed during calibration")
    (output / "calibration.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "calibrate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task", action="append")
    parser.add_argument("--sandbox", type=Path)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args()
    tasks = discover(
        args.root, allowed_splits={"development"} if args.development_only else None
    )
    if args.task:
        tasks = {name: tasks[name] for name in args.task}
    if args.action == "list":
        print(
            json.dumps(
                {
                    "tasks": [
                        {"id": task.name, **task.facets()} for task in tasks.values()
                    ],
                    "families": dict(
                        Counter(task.manifest["family"] for task in tasks.values())
                    ),
                },
                indent=2,
            )
        )
        return 0
    if not args.sandbox or not args.output:
        parser.error("calibration requires --sandbox and --output")
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("calibration requires Linux/Python 3.12")
    result = calibrate(tasks, args.output, args.sandbox, args.toolchain)
    return int(not result["calibrated"])


if __name__ == "__main__":
    raise SystemExit(main())
