# Parallel verifier experiment — 7 September 2026

The explicit verifier completed the workflow; the original verifier failed by
reporting `v-cli` five times. Both candidates passed the same independent checks.
This pair supports the usefulness of spelling out the existing report contract,
but one attempt per condition cannot establish a reliable improvement rate.

| Observation | Original verifier | Explicit verifier |
| --- | ---: | ---: |
| Workflow | Failed | Completed |
| Independent API cases | 14/14 | 14/14 |
| Independent CLI cases | 14/14 | 14/14 |
| Fixed public tests | 3/3 | 3/3 |
| Final `v-unittest` entries | 1 | 1 |
| Final `v-cli` entries | 5 | 1 |
| Model calls | 44 | 25 |
| Tool admissions | 49 | 29 |
| Input tokens, including cached | 458,331 | 209,762 |
| Cached input tokens | 423,050 | 174,902 |
| Output tokens | 15,839 | 14,747 |
| Approval dispatch to process exit | 206.869 s | 139.801 s |
| Files changed, including temporary files | 3 | 24 |
| Diff bytes | 8,214 | 10,773 |

Both executions used Muse `muse-spark-1.3-contributor`, the same canonical plan,
Markdown rendering, planner/executor instructions, clean baseline, model settings,
binary and evaluator. The selected verifier was the only configured variable.
Each used two fresh phase threads, no planner call, no human edit and no amendment.
Preparation used zero model calls/tokens. No execution was retried.

The explicit verifier used one aggregate CLI command covering valid output,
missing input, missing arguments, malformed/non-object JSON, a cycle, an unknown
dependency and extra arguments. It asserted expected exit codes and output bytes
and submitted that completed command's receipt as its single `v-cli` observation.
The unchanged host accepted it. The original failed with
`every planned verification requires one observation`.

## Actual concurrency

The frozen batch coordinator ran with `--jobs 2`. Exact live target approvals were
dispatched one millisecond apart. Both implementation phases started at Unix
millisecond `1788795392874`.

- Host active intervals overlapped for **139.801 seconds**.
- Recorded phase intervals overlapped for **139.387 seconds**.
- Client model-request intervals overlapped for **104.416 seconds**.

The request overlap includes network time and provider queueing; it does not
establish simultaneous server-side computation. Batch exit status is failure
because the original workflow failed. All four phase threads shut down, every
tool admission followed its exact approval, and both candidates were evaluated
after their respective host exits. The successful condition was evaluated while
the other condition was finishing, in its separate locked checkout.

## Limits and observed side effects

The explicit verifier left 21 files under `.tmp_cli_verify/`, accounting for its
24 changed files versus the original's three. The evaluator includes these files
in the final diff. They were preserved without cleanup, so the original outcome
is reproducible. They came from the verifier's aggregate CLI command.

The executor also generated different implementations/test suites in the two
independent samples. Its settings were fixed, but its outputs were not: implementation
took 122.496 seconds in the original condition and 72.437 seconds in the explicit
condition. Verification took 84.222 and 67.016 seconds respectively. Therefore the
total time/token difference is descriptive, not an isolated estimate of verifier
efficiency. The explicit verification phase used more output tokens (7,917 versus
7,034) while using fewer input tokens (93,963 versus 216,341).

The external corpus is finite; passing it does not prove general correctness.
The immutable remote model revision is unknown, plan deviations remain unscored,
and no cumulative spend cap was added. A stronger follow-up would hold the
candidate and implementation evidence fixed for repeated verifier-only trials;
that experiment has not been prepared or authorized. The original verifier and
default workflow remain available, unchanged.

## Evidence and resumption

- [Exact human authorization](execution-approval.json), [reviewed plan](PLAN.md)
  and [preparation/control receipt](preparation.json).
- [Descriptive comparison and artifact hashes](results-2026-09-07.json).
- [Batch configuration](batch-batch.json), [event chronology](batch-events.jsonl)
  and [terminal result](batch-result.json).
- [Model-call timing metadata](model-call-metadata.jsonl), with raw payloads kept local.
- Original: [evaluation](verifier-v1-execution-evaluation.json),
  [shutdown/usage observation](verifier-v1-execution-observation.json),
  [unaltered candidate diff](verifier-v1-execution-candidate.diff).
- Explicit: [evaluation](verifier-single-v2-execution-evaluation.json),
  [shutdown/usage observation](verifier-single-v2-execution-observation.json),
  [unaltered candidate diff](verifier-single-v2-execution-candidate.diff).

Frozen source journals, model payloads and candidates remain under
`/home/james/.cache/codex-lab-verifier-pilot/20260907T153300Z`.
Both approved attempts, independent evaluations and comparison are complete.
No host, pending amendment or retry remains. Do not replay approvals or rerun
collision-refusing launch/export helpers.

Validation covered frozen pins, sealed preparation inventories, exact approval
ordering, complete phase/tool shutdown, live RunSpecs, both independent evaluations,
trace/phase overlap and result hashes. These are results-only repository changes;
no Rust code, core/provider configuration or instruction module changed. The
17,000-test workspace suite was not run.
