"""Additive paired development reports; runtime completion never substitutes for acceptance."""

import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics

from workflows.contracts import RunResult


def comparison(rows, left, right, *, samples=2000, seed=0):
    if not 100 <= samples <= 10000:
        raise ValueError("bounded bootstrap sample count required")
    indexed = {}
    for row in rows:
        key = (row["project_id"], row["fixture"], row["repetition"], row["workflow"])
        if key in indexed:
            raise ValueError("duplicate paired trial identity")
        indexed[key] = row
    pairs, missing = defaultdict(list), 0
    keys = sorted({key[:3] for key in indexed if key[3] in (left, right)})
    for key in keys:
        a, b = indexed.get((*key, left)), indexed.get((*key, right))
        if a is None or b is None:
            missing += 1
            continue
        av, bv = a.get("task_success"), b.get("task_success")
        if any(value is not None and type(value) is not bool for value in (av, bv)):
            raise ValueError("acceptance must be true, false, or unknown")
        choices_a = [int(av)] if av is not None else [0, 1]
        choices_b = [int(bv)] if bv is not None else [0, 1]
        deltas = [y - x for x in choices_a for y in choices_b]
        pairs[key[0]].append((min(deltas), max(deltas)))
    bounds = [
        (statistics.mean(x[0] for x in values), statistics.mean(x[1] for x in values))
        for values in pairs.values()
    ]
    all_known = bool(bounds) and all(low == high for low, high in bounds)
    point = statistics.mean(low for low, _ in bounds) if all_known else None
    outcome_bounds = (
        [
            statistics.mean(low for low, _ in bounds),
            statistics.mean(high for _, high in bounds),
        ]
        if bounds
        else None
    )
    radius = math.sqrt(2 * math.log(40) / len(bounds)) if bounds else None
    interval = None
    if all_known and len(bounds) >= 2:
        randomizer = random.Random(seed)
        values = [low for low, _ in bounds]
        draws = sorted(
            statistics.mean(randomizer.choices(values, k=len(values)))
            for _ in range(samples)
        )
        interval = [
            draws[int(samples * 0.025)],
            draws[min(samples - 1, int(samples * 0.975))],
        ]
    return {
        "left": left,
        "right": right,
        "delta_direction": "right minus left",
        "paired_projects": len(pairs),
        "paired_trials": sum(map(len, pairs.values())),
        "unmatched_trial_keys": missing,
        "unknown_pairs": sum(
            low != high for values in pairs.values() for low, high in values
        ),
        "project_weighted_delta": point,
        "unknown_outcome_bounds": outcome_bounds,
        "project_hoeffding_95_bound": [
            max(-1, outcome_bounds[0] - radius),
            min(1, outcome_bounds[1] + radius),
        ]
        if bounds
        else None,
        "uncertainty_assumption": "independent representative projects; hand-authored development tasks do not establish population generalization",
        "project_bootstrap_95_percent": interval,
        "bootstrap_seed": seed,
        "bootstrap_samples": samples,
        "small_project_count": len(pairs) < 8,
        "inference": "exploratory, not a superiority claim",
    }


def summarize(manifest, result, *, include_strata=True):
    expected = {entry["run_id"]: entry for entry in manifest["trials"]}
    if (
        len(expected) != len(manifest["trials"])
        or result.get("campaign_id") != manifest["campaign_id"]
    ):
        raise ValueError("campaign identity mismatch or duplicate planned run")
    actual = result.get("trials")
    if not isinstance(actual, list) or len({row["run_id"] for row in actual}) != len(
        actual
    ):
        raise ValueError("duplicate or missing result records")
    if {row["run_id"] for row in actual} != set(expected):
        raise ValueError(
            "result must retain every planned trial, including not-started slots"
        )
    rows, arms = [], defaultdict(list)
    for observed in actual:
        planned = expected[observed["run_id"]]
        if any(
            observed.get(key) != planned[key]
            for key in ("workflow", "fixture", "repetition")
        ):
            raise ValueError("trial result differs from planned identity")
        if any(
            key in observed and observed[key] != planned.get(key)
            for key in ("track", "evaluation_group", "pressure")
        ):
            raise ValueError("trial facets differ from frozen plan")
        value = observed.get("task_success")
        if value is not None and type(value) is not bool:
            raise ValueError("invalid acceptance value")
        if observed.get("status") == "not_started" and value is not None:
            raise ValueError("unstarted trial cannot have acceptance")
        normalized = observed.get("workflow_result")
        if normalized is not None:
            verified = RunResult(**normalized)
            if (
                verified.run_id != observed["run_id"]
                or verified.workflow != planned["workflow"]
                or verified.task_id != planned["fixture"]
                or verified.task_success is not value
            ):
                raise ValueError("normalized acceptance identity mismatch")
        elif value is not None:
            raise ValueError("acceptance requires a verified workflow result")
        evidence = (normalized or {}).get("evidence") or {}
        runtime_usage = (
            evidence.get("runtime") or evidence.get("legacy_meter") or {}
        ).get("usage") or {}
        turn_error = evidence.get("turn_error")
        row = {
            **observed,
            "runtime_usage": runtime_usage,
            "failure_phase": observed.get("failure_phase")
            or evidence.get("failure_phase"),
            "turn_error_summary": json.dumps(turn_error, ensure_ascii=False)[:2048]
            if turn_error is not None
            else None,
            "project_id": planned.get("project_id", planned["fixture"]),
            **{
                key: planned.get(key, "unspecified")
                for key in ("track", "evaluation_group")
            },
        }
        rows.append(row)
        arms[row["workflow"]].append(row)
    summaries = {}
    for name, trials in arms.items():
        times = [
            (row["finished_unix_ms"] - row["started_unix_ms"]) / 1000
            for row in trials
            if isinstance(row.get("finished_unix_ms"), int)
            and isinstance(row.get("started_unix_ms"), int)
        ]
        if any(value < 0 for value in times):
            raise ValueError("invalid run timing")
        costs = {}
        for field in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "requests",
            "charged_tokens",
        ):
            values = [
                (
                    (row.get("usage") or {})
                    if field in {"input_tokens", "output_tokens", "cached_input_tokens"}
                    else row["runtime_usage"]
                ).get(field)
                for row in trials
                if row.get("status") != "not_started"
            ]
            if any(
                value is not None and (type(value) is not int or value < 0)
                for value in values
            ):
                raise ValueError("invalid token usage observation")
            costs[field] = {
                "known_total": sum(value for value in values if type(value) is int),
                "unknown_runs": sum(value is None for value in values),
            }
        summaries[name] = {
            "planned": len(trials),
            "accepted": sum(row.get("task_success") is True for row in trials),
            "rejected": sum(row.get("task_success") is False for row in trials),
            "unknown": sum(row.get("task_success") is None for row in trials),
            "not_started": sum(row.get("status") == "not_started" for row in trials),
            "workflow_failed": sum(
                (row.get("workflow_result") or {}).get("workflow_status") == "failed"
                for row in trials
            ),
            "workflow_unknown": sum(
                (row.get("workflow_result") or {}).get("workflow_status") == "unknown"
                for row in trials
            ),
            "wall_seconds_median": statistics.median(times) if times else None,
            "wall_seconds_observed_runs": len(times),
            "usage": costs,
        }
    direct = summaries.get("direct-v1")
    saturated = (
        direct is not None
        and direct["planned"] > 0
        and direct["accepted"] == direct["planned"]
    )
    failures = [
        {
            "run_id": row["run_id"],
            "workflow": row["workflow"],
            "fixture": row["fixture"],
            "accepted": row.get("task_success"),
            "workflow_status": (row.get("workflow_result") or {}).get(
                "workflow_status"
            ),
            "evaluation_exit_code": row.get("evaluation_exit_code"),
            "failure_phase": row.get("failure_phase"),
            "turn_error_summary": row["turn_error_summary"],
            "admission_stopped": row["runtime_usage"].get("admission_stopped"),
            "trial_evidence": str(
                Path(
                    (row.get("analysis_source") or {}).get(
                        "campaign", manifest["output"]
                    )
                )
                / "trials"
                / row["run_id"]
            ),
        }
        for row in rows
        if row.get("task_success") is not True
        or (row.get("workflow_result") or {}).get("workflow_status") != "completed"
    ]
    strata = {}
    if include_strata:
        groups = defaultdict(list)
        for row in rows:
            groups[(row["track"], row["evaluation_group"])].append(row["run_id"])
        for (track, group), ids in sorted(groups.items()):
            subset = summarize(
                {
                    **manifest,
                    "trials": [
                        entry for entry in manifest["trials"] if entry["run_id"] in ids
                    ],
                },
                {
                    **result,
                    "trials": [entry for entry in actual if entry["run_id"] in ids],
                },
                include_strata=False,
            )
            strata[track + " / " + group] = {
                "track": track,
                "evaluation_group": group,
                **{
                    key: subset[key]
                    for key in (
                        "arms",
                        "comparisons",
                        "direct_saturated",
                        "next_decision",
                    )
                },
            }
    return {
        "schema_version": 1,
        "campaign_id": manifest["campaign_id"],
        "study_stage": manifest.get("study_stage", "unspecified"),
        "claim_level": "development observations only; calibration is not held-out evidence",
        "clock": "end-to-end wall time, including provider queue and grading; all observed failures retained",
        "arms": summaries,
        "comparisons": [
            comparison(rows, left, right)
            for left, right in itertools.combinations(sorted(arms), 2)
        ]
        if len(strata) <= 1
        else [],
        "strata": strata,
        "pooling": "Arm totals are descriptive; comparisons and saturation decisions are separated by frozen track and evaluation group. Missing historical metadata stays unspecified.",
        "direct_saturated": None if len(strata) > 1 else saturated,
        "next_decision": "Use the separate track and evaluation-group decisions below; pooled saturation is not applicable."
        if len(strata) > 1
        else "Inspect task relevance and cost differences before scaling the corpus."
        if saturated
        else "Inspect paired failures and task discrimination before choosing a revision.",
        "failure_examples": failures,
    }


def markdown(report):
    lines = [
        "# Development workflow comparison",
        "",
        report["claim_level"],
        "",
        "| Arm | Accepted | Rejected | Acceptance unknown | Workflow failed | Workflow unknown | Not started | Median seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, arm in report["arms"].items():
        seconds = (
            "unknown"
            if arm["wall_seconds_median"] is None
            else f"{arm['wall_seconds_median']:.1f}"
        )
        lines.append(
            f"| {name} | {arm['accepted']} | {arm['rejected']} | {arm['unknown']} | {arm['workflow_failed']} | {arm['workflow_unknown']} | {arm['not_started']} | {seconds} |"
        )
    lines += [
        "",
        "| Arm | Requests known total | Request-unknown runs | Charged tokens known total | Charge-unknown runs |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, arm in report["arms"].items():
        requests, charged = arm["usage"]["requests"], arm["usage"]["charged_tokens"]
        lines.append(
            f"| {name} | {requests['known_total']} | {requests['unknown_runs']} | {charged['known_total']} | {charged['unknown_runs']} |"
        )
    lines += [
        "",
        "Charged tokens include conservative reservations for unknown provider usage; they are not a dollar-price estimate. Missing legacy/SDK usage remains unknown.",
        report["clock"],
        "",
        report["next_decision"],
        "",
        "Paired JSON results weight projects equally, cluster repeated trials by project, retain unknown-outcome bounds, and mark small project counts. No superiority conclusion is drawn.",
    ]
    if report.get("strata"):
        lines += [
            "",
            report["pooling"],
            "",
            "| Track / evaluation group | Arm | Accepted | Rejected | Acceptance unknown |",
            "|---|---|---:|---:|---:|",
        ]
        for name, stratum in report["strata"].items():
            for arm, counts in stratum["arms"].items():
                lines.append(
                    f"| {name} | {arm} | {counts['accepted']} | {counts['rejected']} | {counts['unknown']} |"
                )
        lines.append("")
        for name, stratum in report["strata"].items():
            lines.append(f"- {name}: {stratum['next_decision']}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path, result_path = (
        args.campaign / "campaign.json",
        args.campaign / "results.json",
    )
    manifest_bytes, result_bytes = manifest_path.read_bytes(), result_path.read_bytes()
    report = summarize(json.loads(manifest_bytes), json.loads(result_bytes))
    report["source_sha256"] = {
        "manifest": hashlib.sha256(manifest_bytes).hexdigest(),
        "results": hashlib.sha256(result_bytes).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "report.md").write_text(markdown(report))


if __name__ == "__main__":
    main()
