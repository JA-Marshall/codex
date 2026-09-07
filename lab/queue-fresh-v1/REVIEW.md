# Fresh campaign: 32 trials, 16 concurrent

Prepared and unapproved. No implementation has started. All previous campaign results,
plans, candidates and approvals are excluded. The task remains the durable SQLite queue
and JSON CLI in [CONTRACT.md](../fixtures/durable-queue-v1/project/CONTRACT.md).

## Approval requested

Approve the 32 exact targets in [review-targets.json](review-targets.json) once each,
including the two corrected plans described below. Run at concurrency 16 through the
shared 100 requests/minute Muse proxy. Each trial allows up to two test/fix/retest rounds
under its unchanged approved plan. Material amendments require separate approval.
After hosts stop, independently evaluate candidates and publish all outcomes from this
campaign, including failures. Hidden test results never enter the repair loop.

Batch SHA-256: `75c51b0409949b6c56fef573f3e4624408e387505bd3410de8e79f9455f21acf`.
Only [this batch-input.json](batch-input.json) selects the corrected targets.
The original batch at the campaign root must not launch.

| Combination | Execution IDs |
| --- | --- |
| AAA | queue-r1-aaa-execution, queue-r2-aaa-execution, queue-r3-aaa-execution-reviewed, queue-r4-aaa-execution |
| AAB | queue-r1-aab-execution, queue-r2-aab-execution, queue-r3-aab-execution-reviewed, queue-r4-aab-execution |
| ABA | queue-r1-aba-execution, queue-r2-aba-execution, queue-r3-aba-execution-reviewed, queue-r4-aba-execution |
| ABB | queue-r1-abb-execution, queue-r2-abb-execution, queue-r3-abb-execution-reviewed, queue-r4-abb-execution |
| BAA | queue-r1-baa-execution, queue-r2-baa-execution-reviewed, queue-r3-baa-execution, queue-r4-baa-execution |
| BAB | queue-r1-bab-execution, queue-r2-bab-execution-reviewed, queue-r3-bab-execution, queue-r4-bab-execution |
| BBA | queue-r1-bba-execution, queue-r2-bba-execution-reviewed, queue-r3-bba-execution, queue-r4-bba-execution |
| BBB | queue-r1-bbb-execution, queue-r2-bbb-execution-reviewed, queue-r3-bbb-execution, queue-r4-bbb-execution |

Letters select independent roles: planner A concise / B architecture-first;
executor A conservative / B TDD; verifier A focused / B adversarial.
Markdown representation and model settings are held constant.

## Plans and review findings

Eight fresh planner samples form four blocks. Within each block/planner, four
executor/verifier combinations share the same canonical plan. These shared plans are
not independent planner samples. All eight originals passed schema validation.

- [Block 1 concise](plans/queue-r1-aaa.md)
- [Block 1 architecture](plans/queue-r1-baa.md)
- [Block 2 architecture](plans/queue-r2-baa.md)
- [Block 2 concise](plans/queue-r2-aaa.md)
- [Block 3 architecture](plans/queue-r3-baa.md)
- [Block 3 concise](plans/queue-r3-aaa.md)
- [Block 4 architecture](plans/queue-r4-baa.md)
- [Block 4 concise](plans/queue-r4-aaa.md)

Two plans (block 2 architecture and block 3 concise) incorrectly described 12-key
job views. The contract explicitly lists ten fields. Proposed copies change only
`12-key` to `10-key` in three text fields across those two plans. Eight selected targets
use those copies; originals remain unapproved. See [exact edits](proposed-plan-edits.json)
and [original block 2 architecture](original-plans/queue-r2-baa.json) /
[original block 3 concise](original-plans/queue-r3-aaa.json).
These are proposed assistant corrections, not yet human edits or approvals. If accepted,
record six unchanged planner samples and two approved after correction; do not count all
eight as first-plan approvals. No model retries or old plans were used for corrections.

Review limitation: block 3 concise CHK3 starts with Python help() plus manual checks;
help() alone does not prove behavior. Its regression suite and independent final evaluator
remain required. This procedural weakness is retained as planner output, not silently rewritten.

## Fixed harness and controls

[PR18](https://github.com/JA-Marshall/codex/pull/18) fixes the receipt bug: commands above
8 KiB omit only their preview, preserving host-issued IDs and strict completion evidence.
The new regression failed against old code; 17 focused tests passed with the fix, including
a real-host/sandbox fail/fix/pass loop with a 16 KiB command. Formatting passed; no full suite.
That smoke used a mock model. Live preparation subsequently completed through Muse.

Muse `muse-spark-1.3-contributor`, task baseline, context limits, planner/executor bytes,
v2 verifier bytes, repair budget, renderer and evaluator version are pinned across conditions.
The actual model service may still change behind an alias; no immutable provider version is
claimed. [Effective settings](effective-settings.json), [frozen controls](matrix.json),
[build identity](build.json), [preflight](preflight.json), and [planning metrics](planning-metrics.json)
record the run inputs. Plans differ only across independent planner/block samples.

Execution has 32 total targets, at most 16 active hosts, max_repairs=2, and no replacement
trials or automatic amendment approvals. Existing per-phase/context limits remain.
The recorded 35M aggregate token allocation is advisory, not an enforced token or spend cap.
The proxy counts only traffic routed through its shared endpoint; keep other Muse clients idle.

Campaign root: `/home/james/.cache/codex-lab-queue-matrix/20260907T190853Z-fresh-v1`.
Frozen source: `1adda1a5c0eb708c98380ae92acfa5c3cf320337`.
Binary: `/home/james/.cache/codex-lab-binaries/receipt-fix-v1-20260907/codex-lab`.
Fresh preparation used 208,089 input and 45,526 output tokens.
No task success is claimed before independent evaluation.
