"""Separate observed provider queueing from elapsed time; never infer model speed."""

import argparse
import json
from pathlib import Path
import statistics

from batch_inputs import fingerprint, read_json


def union_ms(intervals):
    total, end = 0, None
    for start, stop in sorted(intervals):
        if stop < start:
            raise ValueError("reversed timing interval")
        total += max(0, stop - max(start, end if end is not None else start))
        end = max(stop, end if end is not None else stop)
    return total


def analyze(batch, events, runtimes, provider):
    names = [entry["run_id"] for entry in batch["runs"]]
    if len(set(names)) != len(names):
        raise ValueError("duplicate run identity")
    bounds, owners, reviews = {}, {}, {}
    for name in names:
        starts = [
            e["unix_ms"]
            for e in events
            if e["type"] == "decision_sent" and e["run_id"] == name
        ]
        stops = [
            e["unix_ms"]
            for e in events
            if e["type"] == "host_exited" and e["run_id"] == name
        ]
        if not starts or len(stops) != 1 or stops[0] < min(starts):
            raise ValueError("timing requires dispatched, exited hosts")
        bounds[name], reviews[name] = (min(starts), stops[0]), len(starts)
        for event in runtimes[name]:
            if event["type"] == "phase_thread_bound":
                thread = event["thread_id"]
                if not thread or thread in owners:
                    raise ValueError("missing or ambiguous phase thread")
                owners[thread] = name
    requests = {}
    for event in provider:
        kind = event["type"]
        if kind not in (
            "request_queued",
            "request_dispatched",
            "request_cancelled",
            "request_finished",
        ):
            continue
        request = event["request_id"]
        if kind == "request_queued":
            if request in requests:
                raise ValueError("duplicate proxy request")
            requests[request] = {"queued": event}
        else:
            if request not in requests or kind in requests[request]:
                raise ValueError("orphan or duplicate proxy observation")
            requests[request][kind] = event
    observed = []
    for request in requests.values():
        queued = request["queued"]
        finish = request.get("request_finished")
        released = request.get("request_dispatched") or request.get("request_cancelled")
        if finish is None or released is None:
            raise ValueError("incomplete proxy request; queue time is unknown")
        wait = released.get("queued_ms", released["unix_ms"] - queued["unix_ms"])
        if (
            type(wait) is not int
            or wait < 0
            or finish["unix_ms"] < released["unix_ms"]
            or abs(released["unix_ms"] - queued["unix_ms"] - wait) > 25
        ):
            raise ValueError("invalid duration or incompatible clocks")
        observed.append(
            {
                "owner": owners.get(queued.get("client_request_id")),
                "start": queued["unix_ms"],
                "end": finish["unix_ms"],
                "wait": wait,
                "queue": (released["unix_ms"] - wait, released["unix_ms"]),
            }
        )
    rows = []
    for name, (start, stop) in bounds.items():
        own = [r for r in observed if r["owner"] == name]
        if not own or any(r["start"] < start - 25 or r["end"] > stop + 25 for r in own):
            raise ValueError("missing requests or requests outside host lifetime")
        intervals = [(max(start, r["queue"][0]), min(stop, r["queue"][1])) for r in own]
        waiting = union_ms(intervals)
        competing = sum(
            r["owner"] != name and r["start"] < stop and r["end"] > start
            for r in observed
        )
        overlapping = any(
            other != name and a < stop and b > start for other, (a, b) in bounds.items()
        )
        reasons = []
        if batch.get("measurement_purpose", "throughput") != "isolated-timing":
            reasons.append("not_declared_isolated_timing")
        if batch["jobs"] != 1 or overlapping:
            reasons.append("concurrent_hosts")
        if competing:
            reasons.append("competing_proxy_requests")
        if reviews[name] != 1:
            reasons.append("additional_human_decisions_in_elapsed_time")
        if any(e["type"] == "runtime_failed" for e in runtimes[name]):
            reasons.append("runtime_failure")
        if any(
            e["type"] == "host_exited"
            and e["run_id"] == name
            and e.get("exit_code") != 0
            for e in events
        ):
            reasons.append("host_failure")
        rows.append(
            {
                "run_id": name,
                "elapsed_ms": stop - start,
                "request_count": len(own),
                "request_wait_sum_ms": sum(r["wait"] for r in own),
                "queue_wait_union_ms": waiting,
                "observed_elapsed_excluding_queue_ms": stop - start - waiting,
                "queue_fraction": waiting / (stop - start) if stop > start else 0,
                "competing_proxy_requests": competing,
                "isolated_timing_eligible": not reasons,
                "exclusion_reasons": reasons,
            }
        )
    return {
        "schema_version": 1,
        "measurement_purpose": batch.get("measurement_purpose", "throughput"),
        "jobs": batch["jobs"],
        "unthrottled_speed_estimate": None,
        "phase_timeout_clock": "wall_clock_including_provider_queue",
        "queue_interval_clock": "wall timestamps checked against monotonic queued_ms; 25ms tolerance",
        "limitations": [
            "Subtraction describes this observed run, not counterfactual unthrottled speed.",
            "Remaining time includes model, tools, network, host overhead and human waits.",
            "Isolation checks see only the supplied proxy trace; use its full experiment interval.",
        ],
        "runs": rows,
    }


def read_jsonl(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("timing input exceeds 32 MiB")
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("partial timing trace")
    return [json.loads(line) for line in data.splitlines()]


def write_report(results, provider, output):
    results, provider, output = results.resolve(), provider.resolve(), output.resolve()
    if (
        output.is_relative_to(results)
        or results.is_relative_to(output)
        or provider.is_relative_to(output)
    ):
        raise ValueError("timing audit must be separate from frozen inputs")
    batch_path, events_path = (
        results / "batch-batch.json",
        results / "batch-events.jsonl",
    )
    batch, batch_hash = read_json(batch_path)
    paths = [batch_path, events_path, provider]
    runtimes = {}
    for entry in batch["runs"]:
        name = entry["run_id"]
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("unsafe run identity")
        path = results / name / "runtime-events.jsonl"
        paths.append(path)
    before = {str(p): fingerprint(p) for p in paths}
    if before[str(batch_path)] != batch_hash:
        raise ValueError("batch changed during analysis")
    for entry in batch["runs"]:
        name = entry["run_id"]
        runtimes[name] = read_jsonl(results / name / "runtime-events.jsonl")
    report = analyze(batch, read_jsonl(events_path), runtimes, read_jsonl(provider))
    report["input_sha256"] = before
    report["analyzer_sha256"] = fingerprint(Path(__file__))
    if before != {str(p): fingerprint(p) for p in paths}:
        raise ValueError("timing inputs changed during analysis")
    output.mkdir(parents=True, exist_ok=False)
    (output / "timing.json").write_text(json.dumps(report, indent=2) + "\n")
    rows = report["runs"]
    text = "# Observed timing audit\n\nShared throttling is included in elapsed time. Queue subtraction is not an unthrottled speed estimate.\n\n"
    text += f"Median queue fraction: {statistics.median(r['queue_fraction'] for r in rows):.1%}. "
    text += f"Isolated timing eligible: {sum(r['isolated_timing_eligible'] for r in rows)}/{len(rows)}.\n\n"
    text += "| Run | Elapsed | Queue wait (union) | Observed remainder |\n| --- | --- | --- | --- |\n"
    for row in rows:
        text += f"| {row['run_id']} | {row['elapsed_ms'] / 1000:.1f}s | {row['queue_wait_union_ms'] / 1000:.1f}s | {row['observed_elapsed_excluding_queue_ms'] / 1000:.1f}s |\n"
    text += "\nThe remainder includes model responses, tool execution and other overhead. Do not rank unconstrained workflow speed from this table. Request-wait sums may double-count overlapping waits; the union does not. The 30-minute phase safety cap includes queue waiting and is not an active-time budget. See [timing.json](timing.json) for provenance and exclusions.\n"
    (output / "README.md").write_text(text)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--provider-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_report(args.results, args.provider_events, args.output)
    print(json.dumps({"runs": len(result["runs"]), "output": str(args.output)}))
