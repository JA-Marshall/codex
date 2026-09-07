"""Audit stopped campaigns with complete provider traces; keep unknown waits unknown."""

import argparse
import json
from pathlib import Path
import re

from batch_inputs import fingerprint, read_json
from timing_report import analyze, read_jsonl


def analyze_campaign(campaign, results, runtimes, provider):
    if (campaign.get("schema_version") != 1 or results.get("schema_version") != 1
            or results.get("campaign_id") != campaign.get("campaign_id")):
        raise ValueError("campaign/result identity or schema mismatch")
    entries = campaign["trials"]
    names = [entry["run_id"] for entry in entries]
    if (not 1 <= len(names) <= 1000 or len(names) != len(set(names))
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name)
                   for name in names)):
        raise ValueError("unsafe or duplicate campaign run identity")
    records = {entry["run_id"]: entry for entry in results["trials"]}
    if set(records) != set(names) or len(records) != len(results["trials"]):
        raise ValueError("campaign/result trial inventory differs")
    purpose = campaign.get("measurement_purpose", "throughput")
    jobs = campaign["jobs"]
    if purpose not in ("throughput", "isolated-timing") or type(jobs) is not int or not 1 <= jobs <= 32:
        raise ValueError("invalid campaign measurement purpose or concurrency")
    if purpose == "isolated-timing" and jobs != 1:
        raise ValueError("isolated-timing requires jobs=1")
    if results.get("measurement_purpose", purpose) != purpose:
        raise ValueError("campaign/result measurement purpose differs")
    for source in (campaign, results):
        if source.get("phase_timeout_clock", "wall_clock_including_provider_queue") != "wall_clock_including_provider_queue":
            raise ValueError("unsupported campaign timeout clock")
    batch = {"runs": [], "jobs": jobs, "measurement_purpose": purpose}
    boundaries, known, unknown, lifetimes = [], {}, {}, {}
    queued_threads = {event.get("client_request_id") for event in provider
                      if event.get("type") == "request_queued"}
    all_threads = set()
    for name in names:
        record, runtime = records[name], runtimes.get(name)
        start, finish = record.get("host_started_unix_ms"), record.get("host_finished_unix_ms")
        reason = None
        if start is None or finish is None:
            reason = "missing_host_lifetime"
        elif type(start) is not int or type(finish) is not int or start < 0 or finish < start:
            raise ValueError("invalid host lifetime")
        elif type(record.get("host_exit_code")) is not int:
            reason = "missing_host_exit"
        elif runtime is None:
            reason = "missing_runtime_evidence"
        if type(start) is int and type(finish) is int and start >= 0 and finish >= start:
            lifetimes[name] = (start, finish)
        threads = [event["thread_id"] for event in runtime or []
                   if event.get("type") == "phase_thread_bound"]
        if (any(not isinstance(thread, str) or not thread for thread in threads)
                or len(threads) != len(set(threads)) or all_threads.intersection(threads)):
            raise ValueError("missing or ambiguous phase thread")
        all_threads.update(threads)
        if reason is None and not queued_threads.intersection(threads):
            reason = "no_observed_model_requests"
        if reason is not None:
            unknown[name] = {
                "run_id": name, "timing_status": "unknown", "timing_unknown_reason": reason,
                "elapsed_ms": finish - start if type(start) is int and type(finish) is int and finish >= start else None,
                **dict.fromkeys(("request_count", "request_wait_sum_ms", "queue_wait_union_ms",
                                 "observed_elapsed_excluding_queue_ms", "queue_fraction", "competing_proxy_requests")),
                "isolated_timing_eligible": False, "exclusion_reasons": [reason],
            }
            continue
        batch["runs"].append({"run_id": name})
        known[name] = runtime
        # These are internal adapter events for the unchanged batch analyzer;
        # they do not assert a human decision occurred in a delegated campaign.
        boundaries.extend([
            {"type": "decision_sent", "run_id": name, "unix_ms": start},
            {"type": "host_exited", "run_id": name, "unix_ms": finish,
             "exit_code": record["host_exit_code"]},
        ])
    # This validates every supplied proxy request, including competing traffic,
    # even when every campaign trial has unknown timing.
    report = analyze(batch, boundaries, known, provider)
    rows = {row["run_id"]: dict(row, timing_status="observed") for row in report["runs"]}
    rows.update(unknown)
    for name in names:
        if name in known:
            start, finish = lifetimes[name]
            if any(other != name and before < finish and after > start
                   for other, (before, after) in lifetimes.items()):
                if "concurrent_hosts" not in rows[name]["exclusion_reasons"]:
                    rows[name]["exclusion_reasons"].append("concurrent_hosts")
                rows[name]["isolated_timing_eligible"] = False
        for field in ("status", "task_success", "host_exit_code", "evaluation_exit_code",
                      "worker_exit_code", "failure_classification"):
            rows[name][field] = records[name].get(field)
    report.update(
        campaign_id=campaign["campaign_id"], runs=[rows[name] for name in names],
        elapsed_basis="host invocation through host exit; fixture setup and independent evaluation excluded",
        unknown_trials=len(unknown), observed_trials=len(known),
        provider_trace_scope="operator-supplied complete immutable trace, including competing traffic",
    )
    report["limitations"].append(
        "Campaign host elapsed includes startup and workflow overhead; it differs from batch first-decision elapsed."
    )
    return report


def write_report(campaign_path, provider_path, output):
    campaign_path, provider_path = campaign_path.resolve(strict=True), provider_path.resolve(strict=True)
    root, output = campaign_path.parent, output.resolve()
    if output.is_relative_to(root) or root.is_relative_to(output) or provider_path.is_relative_to(output):
        raise ValueError("timing output must be separate from campaign and provider inputs")
    results_path, events_path = root / "results.json", root / "events.jsonl"
    campaign, campaign_hash = read_json(campaign_path, limit=8 * 1024 * 1024)
    results, results_hash = read_json(results_path, limit=8 * 1024 * 1024)
    names = [entry["run_id"] for entry in campaign["trials"]]
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name) for name in names):
        raise ValueError("unsafe campaign run identity")
    runtime_paths = {name: root / "runs" / name / "runtime-events.jsonl" for name in names}
    paths = [campaign_path, results_path, events_path, provider_path, *runtime_paths.values()]
    before = {str(path): fingerprint(path) if path.exists() else None for path in paths}
    if before[str(campaign_path)] != campaign_hash or before[str(results_path)] != results_hash:
        raise ValueError("campaign changed during timing observation")
    events = read_jsonl(events_path)
    if (not events or events[0].get("type") != "campaign_started"
            or events[0].get("campaign_id") != campaign["campaign_id"]
            or events[-1].get("type") != "campaign_finished"
            or events[-1].get("total") != len(names)
            or any(event.get("sequence") != index + 1 or event.get("schema_version") != 1
                   for index, event in enumerate(events))):
        raise ValueError("campaign coordinator is not terminal or journal is incomplete")
    runtimes = {name: read_jsonl(path) if path.exists() else None for name, path in runtime_paths.items()}
    report = analyze_campaign(campaign, results, runtimes, read_jsonl(provider_path))
    report["input_sha256"] = before
    report["analyzer_sha256"] = {name: fingerprint(Path(__file__).with_name(name))
                                 for name in ("campaign_timing.py", "timing_report.py", "batch_inputs.py")}
    if before != {str(path): fingerprint(path) if path.exists() else None for path in paths}:
        raise ValueError("timing inputs changed during analysis")
    output.mkdir(parents=True, exist_ok=False)
    (output / "timing.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text = "# Campaign timing audit\n\nElapsed spans host invocation through exit and includes provider queue waiting. Fixture setup and independent evaluation are excluded. Queue subtraction is not an unthrottled speed estimate.\n\n"
    text += "| Run | Timing | Host elapsed (ms) | Queue union (ms) | Observed remainder (ms) |\n| --- | --- | --- | --- | --- |\n"
    for row in report["runs"]:
        values = [str(row[key]) if row[key] is not None else "unknown"
                  for key in ("elapsed_ms", "queue_wait_union_ms", "observed_elapsed_excluding_queue_ms")]
        text += f"| {row['run_id']} | {row['timing_status']} | {' | '.join(values)} |\n"
    text += "\nMissing evidence remains unknown. See [timing.json](timing.json) for input hashes, failures, competing traffic and timing exclusions.\n"
    (output / "README.md").write_text(text, encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--provider-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_report(args.campaign, args.provider_events, args.output)
    print(json.dumps({"runs": len(result["runs"]), "unknown": result["unknown_trials"], "output": str(args.output)}))
