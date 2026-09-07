# Instruction/workflow matrix on a durable queue task

Status: user approved this proposal with Go, including approximately 35M aggregate
reported tokens and preparation concurrency eight. Fixture/evaluator/profile
development and research/planning are authorized. Exact generated-plan execution
targets still require human approval. The ten fixed-candidate verifier trials
remain sealed and unapproved; they are not part of this campaign.

## Experiment

Use Muse Contributor with its existing pinned provider settings. Hold Markdown
constant. Compare eight procedural combinations, with four repetitions each,
for **32 execution trials**, using **8 concurrent isolated hosts**.

| Factor | Variant A | Variant B |
| --- | --- | --- |
| Planner | Concise implementation plan | Architecture/risk-first plan |
| Executor | Conservative minimal-diff procedure | Test-first/TDD procedure |
| Verifier | Focused tests with explicit report contract | Adversarial cases and code review, then explicit report contract |

The full cross-product is A/A/A, A/A/B, A/B/A, A/B/B, B/A/A, B/A/B,
B/B/A and B/B/B. These are explicitly pinned instruction modules selected by
inherited workflow profiles. Both verifier variants retain the already established
one-observation-per-verification-ID contract. Do not change representation, model,
tool availability, approval policy or context limits between combinations.

This first matrix compares instruction procedures within the current enforced
research/plan/approval/implementation/verification state machine. It does not yet
compare different phase graphs. The procedures differ in behavior and wording;
do not interpret an outcome as the effect of verbosity or one phrase alone.

For each of four replicate blocks, research/plan once with each planner: **eight
independent generated plans total**. Import each exact canonical plan into its
four executor/verifier conditions. Research/planning behavior stays independent
of the selected executor and verifier. This yields 32 execution preparations:
eight original generated-plan preparations plus 24 imported-plan preparations.
Treat the four executions sharing a plan as a block, not four independent planner
samples. Record both planner-level and executor/verifier-level effects.

All eight plans and the 32 full target tuples must be available for human review
before implementation. A batch decision may approve an explicit list of targets;
the coordinator still verifies each live run/request/plan/spec identity separately.
No amendment approval or automatic retry is implied. Rejected plans and planning
failures remain observations; do not silently replace them to fill the matrix.

Use a fixed recorded order rotating combinations across blocks, with eight active
jobs. No predecessor-exit barriers. Independent preparation jobs may also run at
concurrency eight once their token budget is authorized. Preserve per-checkout
locks, individual decision channels and natural phase shutdown. Record actual
overlap, provider throttling and scheduling. If a concrete resource/provider limit
prevents eight active jobs, record it and revise the concurrency for the campaign
consistently; do not compare silently mixed scheduling policies.

## Coding task: durable SQLite job queue

Build a partially implemented Python 3.12 standard-library package, not another
single-function puzzle. Preserve its public API/CLI while completing a durable
queue with:

- Atomic batch submission, dependency validation and idempotent job IDs.
- Dependency-aware readiness with deterministic priority/tie-breaking rules.
- Atomic claim operations across two independent worker processes.
- Lease expiry/recovery, attempt limits and bounded retry scheduling.
- Success/failure transitions and durable status across CLI process restarts.
- Transaction rollback on invalid requests and clear JSON CLI output/error codes.

Use an explicit supplied integer clock in tests, fixed IDs and a documented
tie-break rule. Do not depend on real sleeping, external services or installed
third-party packages. Exclude a web UI, daemon, cloud deployment and production
operations. The intended difficulty comes from interacting persistence, state,
concurrency and interface requirements, not vague scope or a huge codebase.

Before generating any model plan, specify the exact API, schema compatibility,
transition table, boundary behavior and CLI contract in TASK.md. Add a small
partially implemented multi-module baseline (storage, queue operations, CLI and
public tests). Freeze the baseline commit and the task bytes. The implementation
under test must be written by each approved model trial, not by the lab author.

Build the independent evaluation corpus before any candidate runs. Include
transaction rollback, duplicate/conflicting submissions, graph readiness,
priority/ties, expiry boundaries, stale completion, retry exhaustion, two-process
claim exclusivity and separate-process CLI durability. Keep expected results and
private cases outside candidate checkouts. Validate the evaluator against a
private reference and deliberately faulty implementations; do not tune cases in
response to model outcomes. Keep task success separate from workflow success.

## Token scale

The last two-run verifier pilot used 698,679 reported input/output tokens combined,
including cached input. Fifty times that is 34,933,950: approximately **35 million
aggregate tokens for the campaign**, if that is the intended interpretation.
This is an allocation, not an instruction to pad prompts or keep working after
completion. It includes research, planning, execution and verification; report
preparation costs separately and never double-count shared plans as new calls.

The user confirmed the aggregate interpretation. Do not infer a dollar ceiling from these token counts: cached input and
provider billing differ. No cumulative hard token/spend limiter exists today.
The initial campaign can release work in reviewed blocks and account for observed
usage, but concurrent in-flight work can exceed an approximate token envelope.
If a strict cap is required, define it and implement/test enforcement before launch;
do not mislabel admission-between-blocks accounting as a per-model-call hard cap.

The current model context is 1,048,576 tokens. The host's 8 KiB instruction/prompt
fragment checks bound injected text, not total model token consumption. Do not
multiply context, permissions, timeout or evidence limits by 50. Keep those controls
fixed; an encountered limit is an experimental outcome until a uniformly revised
campaign is explicitly prepared.

## Actual code seams and implementation stages

1. **Fixture and evaluator foundation.** Add `lab/fixtures/durable-queue-v1/` and
   isolated stateful scenario/worker modules under `lab/experiments/`. Existing
   `fixture_registry.py` and `evaluation_worker.py` assume a single pure-function
   call plus a one-file CLI invocation, which cannot adequately test queue
   durability or cross-process claims. Extend worker selection minimally while
   reusing `evaluate_fixture.py` isolation, timeout/output bounds and the
   `terminal_run.py` shutdown/diff observation. Preserve existing fixture behavior
   and fingerprints; version the new evaluator independently if shared-file changes
   would invalidate old fingerprints.
2. **Pinned procedure modules and profiles.** Add the six explicit role variants
   beneath `lab/instructions/` and a dedicated inherited workflow catalog beneath
   `lab/workflows/`. Keep procedures bounded, non-overlapping and versioned. Reuse
   `WorkflowCatalog::resolve_instructions`; no model-selected skill loading.
3. **Matrix preparation and analysis inputs.** Add a bounded matrix setup adapter
   next to `setup_suite.py`. Avoid expanding the old three-pair hardcoded script.
   Use `prepare` for eight planner samples and `--plan-file` for their 24 clones.
   Seal source commits, task/evaluator/role bytes, exact settings, shared-plan
   lineage, replicate/order identifiers, token allocation and concurrency.
4. **Approve and run.** Reuse `run_batch.py --jobs 8` (already supports up to 32
   hosts/jobs), `run-prepared`, exact human targets, tools and amendments. No
   coordinator rewrite or new TUI is needed. No experiment execution before the
   actual plan/target review.
5. **Evaluate and compare.** Report every failed/rejected/incomplete condition,
   acceptance failures, first-plan approval/edits/amendments, tokens/cache usage,
   calls, wall time, diffs and leftover files. Aggregate by combination and by role,
   preserving plan/replicate blocks and actual concurrency. The existing Rust
   comparison accepts only `plan.renderer`; use a separate matrix report and do
   not mislabel this study as a renderer comparison.

## Maintainability critique and boundaries

The required extension is a richer benchmark adapter and deterministic profiles,
not another rewrite of the Codex driver. No upstream core, provider, auth, sandbox,
Git lifecycle, TUI or subagent changes are planned. Initial phase graph and
verification report protocol remain constant. Defer generic arbitrary-factor
sweeps, a statistical leaderboard, full scheduling recovery and alternate phase
graphs until this concrete matrix exposes a need.

The evaluator is the main new engineering risk: sequential pure-function tests
would miss the task's defining behavior. Establish evaluator isolation and genuine
two-process observations before allocating model calls. A reference and known
faults should exercise those observations offline. Use scoped unit/integration
coverage for these adapters and existing affected evaluator/batch tests; never
run the 17,000-test workspace suite for this campaign.

One task and four planner blocks cannot establish a universal workflow winner.
Report procedure combinations as exploratory evidence, retain all raw artifacts
locally, and publish reproducible metadata and outcomes. Implementation of the
benchmark foundation and model planning are authorized; implementation of generated
candidate plans still requires approval of their exact execution targets.
