"""SDK trial worker under the existing frozen campaign scheduler."""

import fcntl
import json
import os
from pathlib import Path
import sys
import time

from campaign_inputs import validate_pins, write_json
from campaign_service import check_service
from task_registry import (
    load_task,
    setup,
    evaluator_fingerprint,
    inventory as task_inventory,
)
from setup_fixture import git
from workflows.bmad_install import BmadPackage, inventory
from workflows.contracts import RunResult, StudySpec
from workflows.filesystem import SessionSandbox


def run_sdk_trial(manifest, entry):
    study = StudySpec.from_campaign(manifest)
    if entry not in manifest["trials"] or entry["workflow"] not in (
        "direct-v1",
        "bmad-build-auto-v6.12.0",
        "bmad-orchestrated-v6.12.0-recipe1",
        "our-v0",
    ):
        raise ValueError("unrecognized frozen SDK trial")
    directory = Path(manifest["output"]) / "trials" / entry["run_id"]
    with (directory / "started.json").open("x") as receipt:
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
    run, runtime, evaluated, terminal, dispatch = None, None, None, None, None
    project = project_result = None
    phase = "preparation"
    try:
        validate_pins(manifest)
        config = manifest["sdk_runtime"]
        sys.path.insert(0, config["sdk_source"])
        if config.get("sdk_dependencies"):
            sys.path.insert(0, config["sdk_dependencies"])
        from provider_rate_limit import SharedLimiter
        from workflows.metered_run import MeteredRun
        from workflows.session_process import RuntimePin
        from workflows.usage import Budget
        from workflows.bmad import BmadDispatch
        from workflows.evaluation import evaluate_stopped

        pin = RuntimePin(**config["pin"])
        pin.verify()
        task = load_task(
            Path(manifest["task_root"]) / config["task_directories"][entry["fixture"]]
        )
        task_spec = None
        if task.manifest["schema_version"] == 2:
            from task_v2 import TaskSpecV2

            task_spec = TaskSpecV2.load(task.root, task.manifest)
        if task.name != entry["fixture"]:
            raise ValueError("frozen task identity mismatch")
        evolving = task.manifest.get("track") == "B"
        if evolving and (
            entry["workflow"]
            not in ("direct-v1", "bmad-orchestrated-v6.12.0-recipe1", "our-v0")
            or config.get("project_recipe") != "stop-probe-followup-v1"
            or config.get("interaction_policy") != "delegated-task-v1"
        ):
            raise ValueError(
                "evolving tasks require the explicit project recipe and a supported direct or orchestrated arm"
            )
        metadata = setup(directory / "fixture", task, manifest.get("task_toolchain"))
        workspace = Path(metadata["repository"])
        # App-server deliberately receives no host author environment. Configure
        # the disposable repository before its config becomes immutable.
        git(workspace, "config", "user.name", "Codex Lab")
        git(workspace, "config", "user.email", "lab@example.invalid")
        git(workspace, "checkout", "--quiet", "-b", "study/" + task.name)
        starter = inventory(workspace, exclude=(".git",), max_total=32 * 1024 * 1024)
        assets, evaluator = task_inventory(task.root), evaluator_fingerprint()
        installation = None
        if entry["workflow"].startswith("bmad-"):
            package = BmadPackage(
                Path(config["bmad_source"]),
                config["bmad_source_sha256"],
                Path(config["uv"]),
            )
            installation = package.install(workspace, directory / "bmad-installation")
        boundary = installation.sandbox() if installation else SessionSandbox(workspace)
        service = manifest["provider_service"]
        check_service(manifest)
        # Shared service owns the global provider allowance; this relay only
        # accounts for this run. The host-only service key never enters prompts.
        key = os.environ.get(config["service_key_env"], "")
        if not key:
            raise ValueError("shared service credential is unavailable")
        lock_path = workspace / ".git/codex-lab-launch.lock"
        with lock_path.open("x+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if evolving:
                from workflows.evolving_project import EvolvingProject

                project = EvolvingProject(
                    task, Budget(**config["budget"]), directory / "project"
                )
            run_parameters = dict(
                run_id=entry["run_id"],
                pin=pin,
                workspace=workspace,
                artifacts=Path(manifest["output"]) / "runs" / entry["run_id"],
                model=manifest["requested_model"],
                budget=Budget(**config["budget"]),
                shared_upstream=service["base_url"],
                upstream_key=key,
                limiter=SharedLimiter(startup_delay=0),
                sandbox=boundary,
                reasoning_effort=config.get("reasoning_effort", "medium"),
                model_catalog=config.get("model_catalog"),
                allow_workers=installation is not None,
                interaction_policy=config.get("interaction_policy"),
                owner_facts=task_spec.owner_facts if task_spec else (),
                owner_state=project.owner if project else None,
            )
            run = MeteredRun(**run_parameters)
            phase = "workflow"
            record["host_started_unix_ms"] = time.time_ns() // 1000000
            prompt = (workspace / "TASK.md").read_text()
            if config.get("interaction_policy"):
                from workflows.interaction_policy import AUTHORIZATION

                prompt = AUTHORIZATION + "\n\n" + prompt
            evaluation_parameters = dict(
                task=task,
                starter=starter,
                task_assets=assets,
                evaluator=evaluator,
                sandbox=manifest["sandbox"],
                installation=installation,
                toolchain=manifest.get("task_toolchain"),
            )
            if entry["workflow"] == "our-v0":
                from workflows.public_verification import PublicVerifier
                from workflows.our_v0 import OurV0

                public_verifier = PublicVerifier(
                    task, manifest["sandbox"], manifest.get("task_toolchain")
                )
                repair_state = {"used": 0}
            if project:

                def make_increment(index, budget, owner):
                    nonlocal phase, dispatch
                    phase = "workflow"
                    dispatch = None
                    if index == 0:
                        return run
                    return MeteredRun(
                        **{
                            **run_parameters,
                            "budget": budget,
                            "owner_state": owner,
                            "run_id": entry["run_id"] + "-increment-" + str(index),
                            "artifacts": run.artifacts / ("increment-" + str(index)),
                        }
                    )

                def grade_increment(current, reached):
                    nonlocal phase
                    phase = "evaluation"
                    return evaluate_stopped(
                        current, **evaluation_parameters, reached_milestones=reached
                    )

                def invoke_increment(current, text):
                    nonlocal dispatch
                    if entry["workflow"] == "our-v0":
                        dispatch = OurV0(current, public_verifier, repair_state).invoke(
                            text
                        )
                        return {
                            **(dispatch["turn"] or {"status": "failed"}),
                            "workflow_status": dispatch["recipe_status"],
                        }
                    elif entry["workflow"] == "bmad-orchestrated-v6.12.0-recipe1":
                        from workflows.bmad_orchestrated import BmadOrchestrated

                        dispatch = BmadOrchestrated(current, installation).invoke(
                            text, task.name
                        )
                        return {
                            **(dispatch["turn"] or {"status": "failed"}),
                            "workflow_status": dispatch["recipe_status"],
                        }
                    return current.parent(text)

                project_result = project.run(
                    make_increment, invoke_increment, grade_increment
                )
                evaluated, terminal = (
                    project_result["evaluation"],
                    project_result["terminal"],
                )
            else:
                run.start()
                try:
                    if entry["workflow"] == "our-v0":
                        dispatch = OurV0(run, public_verifier, repair_state).invoke(
                            prompt
                        )
                        terminal = dispatch["turn"]
                    elif entry["workflow"] == "bmad-orchestrated-v6.12.0-recipe1":
                        from workflows.bmad_orchestrated import BmadOrchestrated

                        dispatch = BmadOrchestrated(run, installation).invoke(
                            prompt, task.name
                        )
                        terminal = dispatch["turn"]
                    elif installation:
                        dispatch = BmadDispatch(run, installation).invoke(
                            prompt, spec=entry.get("spec_path")
                        )
                        terminal = dispatch["turn"]
                    else:
                        terminal = run.parent(prompt)
                except Exception as error:
                    record["workflow_error"] = str(error)[:2048]
                finally:
                    runtime = run.close()
            record["host_finished_unix_ms"] = time.time_ns() // 1000000
            record["host_exit_code"] = (
                0 if terminal and terminal["status"] == "completed" else 1
            )
            phase = "evaluation"
            if project is None:
                evaluated = evaluate_stopped(run, **evaluation_parameters)
            if evaluated is None:
                raise ValueError("final increment has no confirmed evaluation")
            write_json(directory / "evaluation.json", evaluated)
            record.update(
                status="finished",
                evaluation_exit_code=0,
                task_success=evaluated["task_success"],
                public_test_success=evaluated["public_test_success"],
                hidden_test_success=evaluated["hidden_test_success"],
            )
    except Exception as error:
        record.update(error=str(error)[:2048], failure_phase=phase)
        if phase == "evaluation":
            record["evaluation_exit_code"] = 1
    finally:
        if run is not None:
            try:
                runtime = run.close()
            except Exception as error:
                record["cleanup_error"] = str(error)[:2048]
        if project is not None and project.runtimes:
            from workflows.project_runtime import aggregate_runtime

            runtime = aggregate_runtime(project.runtimes, entry["run_id"])
    stop = runtime["process"]["stop_status"] if runtime else "unconfirmed"
    if runtime and runtime.get("provider_handlers_stopped") is not True:
        stop = "unconfirmed"
    evaluation_status = (
        "completed" if evaluated else "failed" if phase == "evaluation" else "not_run"
    )
    acceptance = (
        evaluated["task_success"] if evaluated and stop == "confirmed" else None
    )
    workflow_status = (
        "completed" if terminal and terminal["status"] == "completed" else "failed"
    )
    if entry["workflow"] in ("bmad-orchestrated-v6.12.0-recipe1", "our-v0"):
        if workflow_status == "completed" and dispatch is not None:
            recipe_status = dispatch["recipe_status"]
            workflow_status = (
                recipe_status if recipe_status in ("completed", "unknown") else "failed"
            )
        else:
            workflow_status = "failed"
    elif entry["workflow"].startswith("bmad-") and workflow_status == "completed":
        claim = (dispatch or {}).get("spec_claim") or {}
        workflow_status = (
            "completed"
            if claim.get("status_claim") == "done"
            else "failed"
            if claim.get("status_claim") == "blocked"
            else "unknown"
        )
    observed = RunResult(
        entry["run_id"],
        entry["workflow"],
        entry["fixture"],
        workflow_status,
        stop,
        evaluation_status,
        evaluated["candidate_sha256"] if evaluated else None,
        acceptance,
        {
            "runtime": runtime,
            "bmad_dispatch": dispatch
            if entry["workflow"].startswith("bmad-")
            else None,
            "our_dispatch": dispatch if entry["workflow"] == "our-v0" else None,
            "project": None
            if project_result is None
            else {
                **{
                    key: project_result[key]
                    for key in (
                        "increments",
                        "reached_milestones",
                        "owner",
                        "all_stopped",
                        "admitted_increments",
                    )
                },
                "recipe": "stop-probe-followup-v1",
                "artifacts": str(project.artifacts),
            },
            "turn_error": terminal.get("error") if terminal else None,
            "failure_phase": record.get("failure_phase"),
        },
    )
    usage = dict(runtime["usage"]) if runtime else None
    if usage is not None:
        complete = usage["unknown_requests"] == 0 and usage["in_flight"] == 0
        usage.update(
            {
                name: usage["observed_" + name] if complete else None
                for name in ("input_tokens", "output_tokens", "cached_input_tokens")
            }
        )
    record.update(
        workflow_result=observed.to_dict(),
        task_success=acceptance,
        usage=usage,
        study_inputs_sha256=study.inputs_sha256,
        finished_unix_ms=time.time_ns() // 1000000,
    )
    write_json(directory / "result.json", record)
    return record
