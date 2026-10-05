"""Use the existing private task grader after the SDK run has stopped."""

import json
from pathlib import Path

from evaluate_task import grade
from task_registry import evaluator_fingerprint, inventory as task_inventory, MAX_TOTAL
from workflows.bmad_install import inventory
from workflows.candidate import capture_product


def evaluate_stopped(
    run,
    task,
    *,
    starter,
    task_assets,
    evaluator,
    sandbox,
    installation=None,
    toolchain=None,
    reached_milestones=None,
):
    try:
        return _evaluate_stopped(
            run,
            task,
            starter=starter,
            task_assets=task_assets,
            evaluator=evaluator,
            sandbox=sandbox,
            installation=installation,
            toolchain=toolchain,
            reached_milestones=reached_milestones,
        )
    except Exception as error:
        directory = run.artifacts / "evaluation"
        directory.mkdir(exist_ok=True)
        result = {
            "evaluation_status": "failed",
            "task_success": None,
            "candidate_sha256": None,
            "error_type": type(error).__name__,
            "error": str(error)[:2048],
        }
        (directory / "failure.json").write_text(json.dumps(result, indent=2) + "\n")
        raise


def _evaluate_stopped(
    run,
    task,
    *,
    starter,
    task_assets,
    evaluator,
    sandbox,
    installation,
    toolchain,
    reached_milestones,
):
    runtime = run.close()
    if task_inventory(task.root) != task_assets or evaluator_fingerprint() != evaluator:
        raise ValueError(
            "private task assets or evaluator changed since trial preparation"
        )
    directory = run.artifacts / "evaluation"
    directory.mkdir(exist_ok=False)
    candidate = directory / "candidate"
    receipt = capture_product(
        run.session.workspace,
        candidate,
        starter=starter,
        write_paths=task.manifest["write_paths"],
        runtime=runtime,
        installation=installation,
    )
    (directory / "snapshot.json").write_text(json.dumps(receipt, indent=2) + "\n")
    interactions = runtime.get("interactions", {})
    behavior = (
        {"asked_facts": interactions["asked_facts"]}
        if "asked_facts" in interactions
        else None
    )
    if reached_milestones is not None:
        behavior = {**(behavior or {}), "reached_milestones": reached_milestones}
    result = grade(candidate, sandbox, task, toolchain, behavior=behavior)
    if (
        inventory(candidate, max_total=MAX_TOTAL) != receipt["product"]
        or task_inventory(task.root) != task_assets
        or evaluator_fingerprint() != evaluator
    ):
        raise ValueError("grading inputs changed during evaluation")
    result.update(
        candidate_sha256=receipt["candidate_sha256"],
        scope_violations=receipt["scope_violations"],
        scope_success=not receipt["scope_violations"],
        evaluation_status="completed",
    )
    result["task_success"] = result["task_success"] and result["scope_success"]
    (directory / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
