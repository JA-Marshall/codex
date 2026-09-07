# Ten verifier-only trials ready for approval

All ten preparations are unapproved and used zero model calls. Approval of this
packet authorizes one attempt per listed target, five per verifier variant, with
`--jobs 2`, followed by independent evaluation and a descriptive comparison.
No automatic retry, planner call, executor call or amendment approval is included.

## Fixed implementation and evidence

Use the original verifier pilot's independently passing candidate, with changes
only in `dependency_order.py`, `cli.py` and `tests/test_regression.py`.
The original workflow failed because its report duplicated IDs; its code passed
all 14 API, 14 CLI and 3 fixed public checks. The candidate is preserved unchanged
in ten fresh clean checkouts at commit
`89d79045aa82411ec7368ecca643562b254ac1f8`.

Review the [source candidate diff](../verifier-pilot/verifier-v1-execution-candidate.diff)
and [source evaluation](../verifier-pilot/verifier-v1-execution-evaluation.json).
The new baseline records those exact bytes in Git; no implementation is regenerated.
The [canonical plan](plan.json) and [Markdown projection](PLAN.md) are unchanged.
The [fixed implementation report and provenance](verification-input.json) are bound
into every approval through digest
`8b417ff4c083e6932929799bbf1768f9be073452828691c7007303caac4d2e9f`.
The full original implementation-phase artifact remains frozen locally; its hash
is recorded alongside the imported report. No prior approval is imported.

After fresh approval, the host records the imported step evidence and starts a
single verification phase. It applies the existing tool/receipt checks. A material
plan amendment stops that trial and requires a fresh preparation; it cannot silently
invoke a planner or executor. Verifiers retain their existing workspace permissions,
so changed source files and leftover temporary files are measured outcomes.

## Controlled difference and targets

Muse `muse-spark-1.3-contributor`, model/provider settings, canonical/rendered plan,
candidate, imported report and all other harness settings are identical. `v1` uses
`verifier/tests-only-v1`; `v2` uses `verifier/tests-only-single-observation-v2`.
The planner/executor instruction selections remain pinned but are not invoked.
Full RunSpecs are identical within each variant, and differ only in seven verifier
selector/instruction/inheritance fields across variants.

Every target has plan ID `task-plan`, revision `1`, content SHA-256
`0eadb6d14529a2989108b40ffbbb8e44bbca0b0be88e776b8424730c74449a53`.

| Variant | Effective run-spec SHA-256 |
| --- | --- |
| `v1` | `35277d0f7f117cd6ceb53397947e91461d206f1bf29e24f75080bfb301463d1f` |
| `v2` | `6c4a326dba18dc22392eb46d10f27348b786bcff29acbc3118f9f706814c86a3` |

The ten exact execution run IDs, in the batch's intended admission order:

1. `verifier-v1-r01-execution`
2. `verifier-v2-r01-execution`
3. `verifier-v2-r02-execution`
4. `verifier-v1-r02-execution`
5. `verifier-v1-r03-execution`
6. `verifier-v2-r03-execution`
7. `verifier-v2-r04-execution`
8. `verifier-v1-r04-execution`
9. `verifier-v1-r05-execution`
10. `verifier-v2-r05-execution`

The complete tuples are in [review-targets.json](review-targets.json). Matching
plan content alone does not approve a target. At launch verify each full live
target and current request number before transmitting its authorized decision.
Admission order alternates variants by replicate; completion order is unrestricted.
Waiting or failed trials must not block unrelated approved trials.

## Validation and resumption

31 focused Rust tests passed: 21 runtime/preparation/driver tests and 10 domain-run
tests. Real-host mock tests cover zero calls before approval, exactly one verifier
phase, imported evidence provenance, sealed input tampering and amendment shutdown
without replanning. Ordinary workflow/preparation regressions passed too. Scoped
Clippy, formatting checks and clean-source build passed; no full workspace suite.

All ten real imported-plan preparations exited 0, with zero phase threads/tokens,
empty runtime traces and no authority. Verified all sealed inventories, instruction
pins, binary/bwrap/interpreter/config/catalog hashes, matching candidate files and
clean Git baselines. [Preparation receipt](preparation.json) records these checks.
Batch preflight accepts all ten isolated checkouts, and no execution directory exists.

Frozen root: `/home/james/.cache/codex-lab-verifier-replays/20260907T155700Z`.
Binary: `/home/james/.cache/codex-lab-binaries/verifier-replay-v1-20260907/codex-lab`,
SHA-256 `dc5b99261abbfb0831836c1586125a3db0a2a4b6f54d51ac26243dedfcfd01d1`,
built from `4804ffae5523318287383375f5b4a270fc9295e7`.

After approval use that root's frozen `inputs/lab/experiments/run_batch.py` with its
`batch-input.json`, `--jobs 2` and fresh output `batch/`. The published
[batch manifest](batch-input.json) is an exact copy. Revalidate all pinned inputs
before launch; keep credentials local. Do not rerun the collision-refusing setup
or export helpers, reopen old sessions or replay historical approvals.

Evaluate every eligible terminal run after confirmed shutdown, using its frozen
fixture manifest and evaluator. This fixture's baseline is the implemented candidate,
so its final diff measures verifier changes and temporary files. Report completion,
report cardinality, correctness, model/tool calls, tokens, wall time and leftover
files per trial. Record actual overlap and scheduling; compare groups descriptively
without the renderer-only comparison CLI. Five trials each remain exploratory;
immutable model revision, provider queueing and cumulative billable spend are not
established by these controls. No cumulative token/spend cap has been added.
