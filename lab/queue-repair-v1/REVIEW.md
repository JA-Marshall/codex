# Approve 32 repair-enabled trials, concurrency 16

**Prepared, unapproved, unlaunched.** Eight planner/executor/verifier combinations,
four executions each, at most sixteen active hosts. Every trial permits an initial
implementation and verification followed by **up to two repair/verification rounds**.
Material plan changes still require separate human approval. A failed trial is
retained; the runner does not automatically start a replacement trial.

## What is being approved

The exact five-field targets are in [review-targets.json](review-targets.json).
Approve each once, with the frozen `max_repairs = 2` policy already bound into its
RunSpec digest. After all runs stop, independently evaluate all final candidates
and publish all outcomes, including failed and exhausted runs.

| Combination | Exact execution target names |
| --- | --- |
| AAA | queue-repair-r1-aaa-execution, queue-repair-r2-aaa-execution, queue-repair-r3-aaa-execution, queue-repair-r4-aaa-execution |
| AAB | queue-repair-r1-aab-execution, queue-repair-r2-aab-execution, queue-repair-r3-aab-execution, queue-repair-r4-aab-execution |
| ABA | queue-repair-r1-aba-execution, queue-repair-r2-aba-execution, queue-repair-r3-aba-execution, queue-repair-r4-aba-execution |
| ABB | queue-repair-r1-abb-execution, queue-repair-r2-abb-execution, queue-repair-r3-abb-execution, queue-repair-r4-abb-execution |
| BAA | queue-repair-r1-baa-execution, queue-repair-r2-baa-execution, queue-repair-r3-baa-execution, queue-repair-r4-baa-execution |
| BAB | queue-repair-r1-bab-execution, queue-repair-r2-bab-execution, queue-repair-r3-bab-execution, queue-repair-r4-bab-execution |
| BBA | queue-repair-r1-bba-execution, queue-repair-r2-bba-execution, queue-repair-r3-bba-execution, queue-repair-r4-bba-execution |
| BBB | queue-repair-r1-bbb-execution, queue-repair-r2-bbb-execution, queue-repair-r3-bbb-execution, queue-repair-r4-bbb-execution |

Letters: planner A concise, B architecture/risk-first; executor A conservative,
B TDD; verifier A focused, B adversarial. Both verifier variants use the corrected
receipt/criterion-ID instructions. All combinations use the same repair policy.

The [batch manifest](batch-input.json) SHA-256 is
`1a09781fc9a867360279a9defe77cc8af1348a7d9c26af71ec1e45976e3508d9`.
Approval excludes superseded sixteen-target preparations, older verifier-only
replays, automatic plan amendments and replacement trials.

## Plans and experimental controls

Canonical plans remain unchanged. Repetitions 1 and 3 import the first prior block;
repetitions 2 and 4 import the second. This gives four executions per combination
using two existing plans per planner, **not four independent planner samples**.
Plans were selected by block order, not candidate outcomes. Previously accepted
corrections remain part of the architecture plans. No candidate bug-fix hints or
hidden-test answers were added to the model instructions.

Read [block 1 concise](plans/queue-r1-aaa.md),
[block 1 architecture](plans/queue-r1-baa.md),
[block 2 concise](plans/queue-r2-aaa.md), and
[block 2 architecture](plans/queue-r2-baa.md). Canonical JSON is stored alongside.

Muse `muse-spark-1.3-contributor`, provider/catalog, model/context settings, task
baseline `689b3bd49dd3ef4f746481e909edfad041ab16b0`, planner/executor bytes and
Markdown representation remain unchanged. The runtime binary changes to support
repair, and its identity correctly changes the effective-settings hash. All other
effective settings were compared field by field. Evaluator `durable-queue-v2`
includes the JSON serialization correction; its private corpus remains unchanged.
Repair policy, verifier instructions and concurrency differ from the earlier
campaign, so old/new outcomes are exploratory rather than a single-variable test.

Repair is triggered by failed commands referenced in a valid verification report.
Malformed reports, runtime/shutdown failures and missed bugs do not trigger repair.
Each repair clears stale step/check completion and requires fresh evidence. Failed
check IDs enter a bounded prompt; the executor diagnoses them in the checkout.
Hidden evaluation happens only after execution and is never fed back into repairs.
Candidate diffs and check results are checkpointed at each valid verification round.
Every phase, repair transition, model call and final outcome remains attributable.

Prior execution averaged about 1.31M tokens per trial: 32 comparable initial runs
would be roughly 42M tokens, **plus repairs**. This is an estimate including cached
input, not a hard cap or dollar-cost estimate. At most three implementation and
three verification rounds per unamended trial; the existing whole-run phase bound
and per-phase/context limits remain. No hard cumulative token/spend cap exists.

## Validation and resumption

54 scoped tests passed (24 domain/config/run; 30 runtime), including actual Codex
host/mock-model repair success, disabled/exhausted budgets, amendments and exact
approval enforcement, report validation, prepared runs and verifier-only replay.
Scoped lint fixes, formatting checks and clean-source build passed. No full
workspace suite or tests after formatting. The earlier seven evaluator tests cover
the unchanged v2 evaluator. Build identity is in [build.json](build.json).

All 32 imported preparations have zero model calls/tokens/phase threads, empty
runtime traces, no human approvals, sealed inventories, byte-identical plans and
clean task checkouts. Preflight accepts 32 distinct targets at jobs=16. Initial
preparation stopped after 17 imports because its comparison still expected the old
binary hash. The settings difference was inspected and verified to be only runtime
binary identity; the completion helper retained those 17 and imported the remaining
15 once. No model execution was attempted, failed, replaced or retried.

Campaign root: `/home/james/.cache/codex-lab-queue-matrix/20260907T181937Z-repair-v1`.
Frozen source: `dc83f4578b88c2a0c122e376f717fb286e46ff9a`.
Binary: `/home/james/.cache/codex-lab-binaries/repair-v1-20260907/codex-lab`.
Binary SHA-256: `b9739a0315301c82b4ba84450a40470da94fd6608deb0425c81fb17c8ef9e9b0`.
See [preparation receipt](preparation.json), [conditions](conditions.json),
[frozen controls](matrix.json), and [preflight](preflight.json).

After explicit approval of these targets, revalidate all pins and descriptors,
launch the frozen `inputs/lab/experiments/run_batch.py` with `--jobs 16`, a fresh
`batch` destination, and the recorded manifest. Match each live review request to
the new exact approval; never reuse old authority. Keep amendments separate and
let unrelated approved runs proceed. Once every host and phase has stopped, use
the frozen evaluator and preserve terminal observations and all checkpoint/final
diffs. Helpers are archived for provenance and must not be blindly rerun.
