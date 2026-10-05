"""Report queue lineage and explicit, hash-bound oracle corrections additively."""

import argparse
import copy
import json
from pathlib import Path

from campaign_inputs import digest, read_json, validate_pins
from study_report import markdown, summarize


def load_lineage(directory, depth=0):
    if depth >= 8:
        raise ValueError("queue lineage exceeds eight campaigns")
    directory = Path(directory).resolve(strict=True)
    manifest_path, result_path = directory / "campaign.json", directory / "results.json"
    manifest = read_json(manifest_path)
    if manifest.get("study_stage") in ("validation", "confirmation"):
        raise ValueError("held-out feedback requires the custodian release boundary")
    result = read_json(result_path)
    summarize(manifest, result)
    source = dict(
        campaign=str(directory),
        manifest_sha256=digest(manifest_path),
        results_sha256=digest(result_path),
    )
    for row in result["trials"]:
        row["analysis_source"] = source
    parent = manifest.get("queue_resume")
    if not parent:
        return manifest, result, [source]
    parent_path = Path(parent["parent_manifest"])
    if digest(parent_path) != parent["parent_manifest_sha256"]:
        raise ValueError("queue parent evidence changed")
    previous_manifest = read_json(parent_path)
    if previous_manifest.get("study_stage") in ("validation", "confirmation"):
        raise ValueError("held-out feedback requires the custodian release boundary")
    if digest(parent_path.parent / "results.json") != parent["parent_results_sha256"]:
        raise ValueError("queue parent evidence changed")
    previous_result = read_json(parent_path.parent / "results.json")
    from study_resume import derive_child

    claim = read_json(parent_path.parent / "queue-resume-claim.json")
    if (
        claim.get("output") != str(directory)
        or claim.get("parent_manifest_sha256") != parent["parent_manifest_sha256"]
        or claim.get("parent_results_sha256") != parent["parent_results_sha256"]
        or claim.get("run_ids") != parent["run_ids"]
    ):
        raise ValueError("child does not match the exclusive parent queue claim")
    pending = [
        row
        for row in previous_manifest["trials"]
        if row["run_id"] in set(claim["run_ids"])
    ]
    if manifest != derive_child(
        previous_manifest,
        parent_path,
        directory,
        pending,
        claim,
        manifest["campaign_id"],
    ):
        raise ValueError("queue child changed frozen comparison conditions")
    validate_pins(previous_manifest)
    validate_pins(manifest)
    expected = {row["run_id"]: row for row in previous_manifest["trials"]}
    previous = {row["run_id"]: row for row in previous_result["trials"]}
    if set(parent["run_ids"]) != {row["run_id"] for row in manifest["trials"]}:
        raise ValueError("child plan differs from queue claim")
    for row in manifest["trials"]:
        if (
            row != expected.get(row["run_id"])
            or previous[row["run_id"]].get("status") != "not_started"
        ):
            raise ValueError("queue child changed or retried a parent slot")
    root, combined, sources = load_lineage(parent_path.parent, depth + 1)
    replacements = {row["run_id"]: row for row in result["trials"]}
    combined["trials"] = [
        replacements.get(row["run_id"], row) for row in combined["trials"]
    ]
    summarize(root, combined)
    return root, combined, sources + [source]


def apply_correction(result, directory, expected_manifest, expected_results, sources):
    directory = Path(directory).resolve(strict=True)
    manifest_path, results_path = (
        directory / "manifest.json",
        directory / "results.json",
    )
    if (
        digest(manifest_path) != expected_manifest
        or digest(results_path) != expected_results
    ):
        raise ValueError(
            "oracle correction differs from the explicitly selected hashes"
        )
    manifest, replay = read_json(manifest_path), read_json(results_path)
    if replay.get("model_calls") != 0 or manifest.get(
        "original_campaign_sha256"
    ) not in {source["manifest_sha256"] for source in sources}:
        raise ValueError(
            "correction must bind this campaign and contain zero model calls"
        )
    entries = {row["run_id"]: row for row in manifest["entries"]}
    corrections = replay["records"]
    if len({row["run_id"] for row in corrections}) != len(corrections) or {
        row["run_id"] for row in corrections
    } != set(entries):
        raise ValueError("duplicate or mismatched correction records")
    rows = {row["run_id"]: row for row in result["trials"]}
    audit = []
    for correction in corrections:
        identity = correction["run_id"]
        row, entry = rows[identity], entries[identity]
        original_path = (
            Path(row["analysis_source"]["campaign"])
            / "trials"
            / identity
            / "result.json"
        )
        if (
            Path(entry["original_result"]).resolve() != original_path.resolve()
            or digest(original_path) != entry["result_sha256"]
            or entry["result_sha256"] != correction["original_result_sha256"]
        ):
            raise ValueError("correction original result mismatch")
        original = read_json(original_path)
        if original.get("workflow_result") != row.get(
            "workflow_result"
        ) or original.get("task_success") is not row.get("task_success"):
            raise ValueError("aggregate differs from corrected original result")
        normalized = row["workflow_result"]
        if (
            correction["replay_manifest_sha256"] != expected_manifest
            or correction["candidate_sha256"] != normalized["candidate_sha256"]
            or correction["original_workflow_status"] != normalized["workflow_status"]
            or correction["original_task_success"] is not row["task_success"]
        ):
            raise ValueError("correction candidate or original outcome mismatch")
        original_evaluation = Path(entry["original_evaluation"])
        if (
            digest(original_evaluation) != entry["evaluation_sha256"]
            or entry["evaluation_sha256"] != correction["original_evaluation_sha256"]
            or digest(entry["snapshot"]) != entry["snapshot_sha256"]
        ):
            raise ValueError("correction original evaluation or snapshot changed")
        evaluation = read_json(original_evaluation)
        if (
            normalized["stop_status"] != "confirmed"
            or normalized["evaluation_status"] != "completed"
            or evaluation.get("scope_success")
            is not correction["original_scope_success"]
        ):
            raise ValueError("correction lacks matching stopped evaluation/scope")
        if (
            type(correction["original_scope_success"]) is not bool
            or type(correction["evaluation"]["task_success"]) is not bool
        ):
            raise ValueError("correction acceptance inputs must be booleans")
        accepted = correction["corrected_task_success"]
        if type(accepted) is not bool or accepted is not (
            correction["evaluation"]["task_success"]
            and correction["original_scope_success"]
        ):
            raise ValueError("corrected acceptance conflicts with replay checks/scope")
        audit.append(
            dict(
                run_id=identity,
                original_task_success=row["task_success"],
                corrected_task_success=accepted,
                oracle_revision=correction["oracle_revision"],
                correction_results=str(results_path),
            )
        )
        row["task_success"] = accepted
        normalized["task_success"] = accepted
    return dict(
        manifest=str(manifest_path),
        manifest_sha256=expected_manifest,
        results_sha256=expected_results,
        records=audit,
        semantics="derived analysis only; original results and workflow status unchanged",
    )


def compare(directory, output, correction=None):
    manifest, result, sources = load_lineage(directory)
    analysis = copy.deepcopy(result)
    raw = summarize(manifest, result)
    amendment = apply_correction(analysis, *correction, sources) if correction else None
    report = summarize(manifest, analysis)
    report.update(
        sources=sources,
        queue_lineage="parent outcomes reused as the same original slots, never fresh repetitions",
        oracle_correction=amendment,
    )
    if amendment:
        report["original_oracle_counts_not_quality_failures"] = raw["arms"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    notes = (
        "\nQueue lineage retains original parent slots; they are not new repetitions.\n"
        if len(sources) > 1
        else ""
    )
    if amendment:
        notes += "\nAcceptance uses the explicitly selected oracle correction; original raw failures are not quality failures.\n"
        for row in amendment["records"]:
            notes += f"- {row['run_id']}: original {row['original_task_success']}, corrected {row['corrected_task_success']} ({row['oracle_revision']}); {row['correction_results']}\n"
    (output / "report.md").write_text(markdown(report) + notes)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--correction", type=Path)
    parser.add_argument("--correction-manifest-sha256")
    parser.add_argument("--correction-results-sha256")
    args = parser.parse_args()
    values = (
        args.correction,
        args.correction_manifest_sha256,
        args.correction_results_sha256,
    )
    if any(values) and not all(values):
        parser.error(
            "correction requires directory and both explicitly selected hashes"
        )
    compare(args.campaign, args.output, values if all(values) else None)


if __name__ == "__main__":
    main()
