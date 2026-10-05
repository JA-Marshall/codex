"""Exercise milestone delivery using offline reference increments and real grading."""

import hashlib
import json
import shutil

from evaluate_task import evaluate
from provider_proxy import Journal
from task_registry import inventory
from workflows.milestones import Milestones


def calibrate_changes(
    task, directory, repository, sandbox, toolchain, variant, behavior, overlay
):
    journal = Journal(directory / "reference-changes.jsonl")
    gate = Milestones(task, journal)
    try:
        for change in gate.spec.changes:
            if variant not in ("baseline", "irrelevant-patch"):
                overlay(task.root / "private/checkpoints" / change["after"], repository)
            destination = directory / "milestones" / change["after"]
            destination.parent.mkdir(exist_ok=True)
            result = evaluate(
                repository,
                sandbox,
                destination,
                directory / "fixture.json",
                toolchain=toolchain,
                behavior={**behavior, "reached_milestones": list(gate.delivered)},
            )
            candidate = destination / "candidate"
            candidate.mkdir()
            for name in result["candidate_files"]:
                target = candidate / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repository / name, target)
            if inventory(candidate) != result["candidate_files"]:
                raise ValueError("offline milestone snapshot differs from graded bytes")
            result["candidate_sha256"] = hashlib.sha256(
                json.dumps(
                    result["candidate_files"], sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            (destination / "snapshot.json").write_text(
                json.dumps(
                    {
                        "source": "offline calibration, no model runtime",
                        "candidate_files": result["candidate_files"],
                        "candidate_sha256": result["candidate_sha256"],
                    },
                    indent=2,
                )
                + "\n"
            )
            brief = gate.advance(result)
            if brief is None:
                break
            (destination / "delivered-change.txt").write_text(brief)
        return {**behavior, "reached_milestones": list(gate.delivered)}
    finally:
        journal.stream.close()
