# Timing under a shared provider limit

Use parallel batches to compare task correctness, verification quality, tokens and shared throughput. Their elapsed times include contention for the same Muse allowance and cannot establish unconstrained workflow speed.

The batch coordinator records an explicit measurement purpose. Existing invocations default to `throughput`; parallelism remains available:

```sh
python3.12 lab/experiments/run_batch.py batch-input.json --purpose throughput --jobs 16 --output batches/quality-001
```

For a separate timing campaign, use fresh prepared targets and approvals:

```sh
python3.12 lab/experiments/run_batch.py timing-input.json --purpose isolated-timing --jobs 1 --output batches/timing-001
```

`isolated-timing` rejects any other job count before starting a host. Keep model/version, task, commit, instructions, limits and provider policy fixed; balance condition order across repetitions to reduce time/order effects. Keep other clients off the shared proxy during timing runs. One local job cannot guarantee isolation from external account traffic or provider load. The limiter remains enabled for account compliance.

## Audit recorded runs

The offline analyzer consumes the published result layout: `batch-batch.json`, `batch-events.jsonl` and `RUN_ID/runtime-events.jsonl`. Supply the complete proxy trace covering the experiment, including competing traffic, rather than a trace filtered to selected runs:

```sh
python3.12 lab/experiments/timing_report.py --results lab/queue-fresh-v1/results --provider-events lab/queue-fresh-v1/results/provider-events.jsonl --output lab/queue-fresh-v1/timing-audit-v1
```

The output must be new and separate from frozen inputs. It records input and analyzer hashes, observed host overlap, competing proxy requests and reasons a run is unsuitable for isolated timing. Incomplete request evidence fails analysis rather than becoming zero queue time. Trace completeness and external traffic still require operator control.

| Metric | Meaning |
| --- | --- |
| Elapsed | First dispatched human decision through host exit; initial review waiting is excluded. |
| Request wait sum | Sum of every request's logged queue duration; concurrent waits can overlap. |
| Queue wait union | Duration covered by at least one queue interval within the host lifetime; overlaps count once. |
| Observed remainder | Elapsed minus queue union in this recorded run. It includes model, tools, network, overhead and any later human waits. |

The remainder is not model compute time or a prediction of unthrottled speed. A queued request can overlap useful work elsewhere in its host. Preserve actual elapsed time, and do not use subtraction to manufacture a speed ranking. Timing eligibility also does not imply task success; use the independent evaluator for that.

## Timeouts

The existing 30-minute phase timeout remains a wall-clock safety cap, including provider queueing. This change does not pause it or introduce an active-time execution budget. The completed campaign remains frozen under its original timeout policy. A future queue-aware execution budget would need trusted live wait accounting and separate safety limits, plus a newly pinned campaign configuration.

The reporting calculation was introduced in commit `a359dd91e5` and is reused here unchanged.

## Unattended repository campaigns

`run_campaign.py` accepts the same `--purpose throughput|isolated-timing` setting. Isolated timing
requires `--jobs 1` before any trial is admitted. The frozen manifest and results record the
purpose and the wall-clock timeout policy. Each trial records host invocation and exit separately
from fixture setup and independent grading.

After the entire campaign stops, copy a complete provider event trace, including competing
traffic, to an immutable file and run:

```sh
python3.12 lab/experiments/campaign_timing.py \
  --campaign /path/to/campaign.json \
  --provider-events /path/to/provider-events.jsonl \
  --output /path/to/new-timing-report
```

The campaign adapter reuses the existing queue-union calculation. Missing host or request evidence
produces an explicit unknown timing result; incomplete or inconsistent provider traces are rejected.
Elapsed time here covers the complete host invocation, including planning and startup, rather than
the older human-approved batch's first-decision boundary. A single worker does not remove competing
traffic from the shared limiter; the report flags that traffic instead of claiming isolated speed.

The earlier 200-trial task-library preparation remains frozen with its original scripts. It must
be replaced by a new preparation to use this timing adapter. The [corrected two-trial live smoke](TASK_LIBRARY_SMOKE.md)
passed, and a new v2 200-trial preparation is ready but unstarted. Neither the limiter policy nor
the phase timeout was changed.
