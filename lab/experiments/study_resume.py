"""Prepare a fresh campaign for never-started slots, without restarting agents."""

import copy
import json
from pathlib import Path
import shutil
import uuid

from campaign_inputs import digest, load_campaign, read_json, write_json


def derive_child(parent, parent_path, output, pending, claim, identity):
    old, new = str(Path(parent_path).parent), str(output)

    def relocate(value):
        if isinstance(value, str):
            return (
                new + value[len(old) :]
                if value == old
                or value.startswith(old + "/")
                or value.startswith(old + "\\")
                else value
            )
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, dict):
            return {relocate(key): relocate(item) for key, item in value.items()}
        return value

    child = relocate(copy.deepcopy(parent))
    child.pop("manifest_sha256", None)
    child.update(
        campaign_id=identity,
        trials=relocate(pending),
        queue_resume=dict(
            claim,
            parent_manifest=str(parent_path),
            semantics="only never-started slots; no consumed budget is reset",
        ),
    )
    if "storage_policy" in child:
        selected = set(claim["run_ids"])
        child["storage_policy"]["full_trace_sample"] = [
            name
            for name in child["storage_policy"]["full_trace_sample"]
            if name in selected
        ]
    return child


def prepare_resume(parent_path, output):
    parent_path = Path(parent_path).resolve(strict=True)
    if read_json(parent_path).get("study_stage") in ("validation", "confirmation"):
        raise ValueError(
            "held-out resume requires custodian preregistration and reservation"
        )
    parent = load_campaign(parent_path)
    directory = parent_path.parent
    result_path = directory / "results.json"
    result = read_json(result_path)
    if result.get("campaign_id") != parent["campaign_id"]:
        raise ValueError("parent result identity mismatch")
    events_path = directory / "events.jsonl"
    if events_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("campaign event journal exceeds bound")
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    if not events or events[-1].get("type") != "campaign_finished":
        raise ValueError("queue resume requires a terminal campaign")
    expected = {entry["run_id"]: entry for entry in parent["trials"]}
    records = {row["run_id"]: row for row in result["trials"]}
    if set(records) != set(expected) or len(records) != len(result["trials"]):
        raise ValueError("parent result must account for every planned slot once")
    started = {
        event.get("run_id") for event in events if event.get("type") == "trial_started"
    }
    pending = []
    for identity, row in records.items():
        if row.get("status") == "not_started":
            if (
                identity in started
                or (directory / "trials" / identity / "started.json").exists()
                or (directory / "runs" / identity).exists()
                or (directory / "trials" / identity / "legacy-meter").exists()
            ):
                raise ValueError(
                    "a previously started trial cannot receive a fresh budget"
                )
            pending.append(expected[identity])
        else:
            normalized = row.get("workflow_result") or {}
            runtime = (normalized.get("evidence") or {}).get("runtime") or {}
            if runtime:
                confirmed = (
                    normalized.get("stop_status") == "confirmed"
                    and runtime.get("provider_handlers_stopped") is True
                )
            else:
                from workflows.legacy import LegacyWorkflowAdapter

                verified = (
                    LegacyWorkflowAdapter()
                    .collect(
                        row,
                        directory / "trials" / identity,
                        (
                            directory
                            / "trials"
                            / identity
                            / "legacy-meter/runs"
                            / identity
                        )
                        if parent.get("legacy_runtime")
                        else directory / "runs" / identity,
                    )
                    .to_dict()
                )
                confirmed = (
                    verified == normalized and verified["stop_status"] == "confirmed"
                )
            if not confirmed:
                raise ValueError(
                    "all started parent trials need confirmed shutdown before queue resume"
                )
    if not pending:
        raise ValueError("no never-started slots remain")
    output = Path(output).resolve()
    if (
        output.exists()
        or output.is_relative_to(directory)
        or directory.is_relative_to(output)
    ):
        raise ValueError("resume output must be a fresh disjoint directory")
    claim = dict(
        parent_manifest_sha256=digest(parent_path),
        parent_results_sha256=digest(result_path),
        run_ids=[entry["run_id"] for entry in pending],
        output=str(output),
    )
    # Exclusive parent claim prevents preparing the same pending slots twice.
    # Failed preparation leaves this claim visible and requires manual recovery.
    with (directory / "queue-resume-claim.json").open("x", encoding="utf-8") as stream:
        json.dump(claim, stream, indent=2)
    output.mkdir(parents=True)
    shutil.copytree(directory / "inputs", output / "inputs", symlinks=True)
    child = derive_child(parent, parent_path, output, pending, claim, str(uuid.uuid4()))
    child_path = output / "campaign.json"
    write_json(child_path, child)
    load_campaign(child_path)
    return child_path
