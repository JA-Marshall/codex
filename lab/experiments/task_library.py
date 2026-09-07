"""List coding tasks or calibrate their graders offline before model experiments."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

from evaluate_task import evaluate
from task_registry import discover, inventory, setup


def overlay(source, destination):
    for name in inventory(source):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)


def calibrate(tasks, output, sandbox, toolchain=None):
    output = Path(output).resolve()
    if any(output.is_relative_to(task.root) or task.root.is_relative_to(output) for task in tasks.values()):
        raise ValueError("calibration output must not overlap task assets")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name, task in tasks.items():
        selected_toolchain = toolchain if task.manifest["language"] == "rust" else None
        root = output / name
        root.mkdir()
        variants = ["baseline", "solution", *task.manifest["mutants"]]
        for variant in variants:
            directory = root / variant
            metadata = setup(directory, task, selected_toolchain)
            repository = Path(metadata["repository"])
            if variant != "baseline":
                overlay(task.root / "solution", repository)
            if variant not in ("baseline", "solution"):
                overlay(task.root / "mutants" / variant, repository)
            result = evaluate(repository, sandbox, directory / "evaluation",
                              directory / "fixture.json", toolchain=selected_toolchain)
            expected = variant == "solution"
            record = {"task": name, "variant": variant, "expected_pass": expected,
                      "actual_pass": result["task_success"],
                      "calibrated": result["task_success"] is expected,
                      "evaluation": str(directory / "evaluation/evaluation.json")}
            records.append(record)
            print(json.dumps(record), flush=True)
    result = {"schema_version": 1, "tasks": len(tasks), "variants": len(records),
              "calibrated": all(record["calibrated"] for record in records),
              "model_calls": 0, "records": records}
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
    args = parser.parse_args()
    tasks = discover(args.root)
    if args.task:
        tasks = {name: tasks[name] for name in args.task}
    if args.action == "list":
        print(json.dumps({"tasks": [{"id": task.name, **task.facets()} for task in tasks.values()],
                          "families": dict(Counter(task.manifest["family"] for task in tasks.values()))}, indent=2))
        return 0
    if not args.sandbox or not args.output:
        parser.error("calibration requires --sandbox and --output")
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("calibration requires Linux/Python 3.12")
    result = calibrate(tasks, args.output, args.sandbox, args.toolchain)
    return int(not result["calibrated"])


if __name__ == "__main__":
    raise SystemExit(main())
