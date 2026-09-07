**Implementation plan: useful unattended workflow experiments**

Prepared 7 September 2026. Updated implementation status: integration is complete;
the current increment adds a 20-task Python/Rust library, repository-task adapters,
scope controls, and two generic workflows with zero or one repair. Final shared
WSL sandbox calibration passed all 80 expected variant outcomes with zero model calls.
Final lint/format/build checks passed. The separate release and 200-trial offline preparation are complete;
their identities are recorded in [the release receipt](task-library-release-2026-09-07.json).
The actual inventory, interfaces, evidence limits, and artifact locations
are recorded in [TASK_LIBRARY.md](TASK_LIBRARY.md). The earlier installed release and its focused
checks are recorded in
[unattended-integration-2026-09-07.json](unattended-integration-2026-09-07.json).
No live study has started. The larger handover/context study described below remains
proposed work; it is not the two-workflow task-library preparation.

The objective is to identify which working methods finish repository tasks
correctly, how much additional checking and repair costs, and how reliably those
methods work without human intervention. A plan is one input to that process.

Revised after the user's scope-creep clarification: keep separate, bounded agents
as a design requirement. The broader proposed study compares handover information and
repair, replacing the earlier tests-first/implementation-first matrix. The current
increment holds generic role instructions fixed and varies only zero versus one repair. A single
continuous agent is outside this study. Give workers enough information to do
their assigned job while keeping their authority narrow and independently defined.

**1. Integrate the working infrastructure into a new release**

Integration completed in the isolated `lab/workflow-study-integration` worktree.
The installed binary and scripts were built from `5b49e33011`:

| Source | Available behavior | Integration result |
| --- | --- | --- |
| Main line at `af8e801341` | Bounded repair, corrected evaluator, shared provider limiter, long-command receipt fix | Used as the integration base. |
| `lab/unattended-campaign` at `0ed28fdc5a` | Delegated plan decisions, frozen campaigns, bounded queue, independent grading of failed hosts | Feature commits ported; newer receipt/repair behavior preserved. |
| Installed unattended v2 launcher | Queues a finite campaign with no plan prompts | New versioned bundle and separate provider home validated with a 200-trial offline preparation. |

The integration used a dedicated worktree and separate build mirror. Earlier
tasks retain their frozen binaries, source snapshots, provider configuration and
output directories. The new `muse-contributor-unattended-v2` home follows the
limited profile with a separate model catalog describing delegated authorization.
It uses the existing shared proxy, which was not restarted. New Muse campaigns
require the service receipt and matching provider URL, with a local health check
before worker admission and host launch. Record overlapping workload and provider
waiting time where attributable when live studies begin.

Keep changes primarily in `codex-rs/lab`, `codex-rs/lab-runtime` and
`lab/experiments`. Continue using upstream execution, sandbox and model interfaces.
Retain the distinction between historical human approvals and explicitly delegated
new campaigns. The earlier experiment reset still applies: historical results are
debugging evidence and are excluded from new comparisons.

Validation passed: 36 selected Rust tests and 27 unique Python tests, scoped strict
Clippy and formatting. The real mock-provider host completed
research/plan/implement/fail/repair/pass with stdin closed and commands longer
than 16 KiB. Queue and proxy tests covered isolated failures, bounded admission,
shared allowance and rejection of direct Muse routing. The package records binary
and source hashes. The Windows launcher froze 200 trials with concurrency 16;
all 71 input pins matched and the existing service reported ready. This made no
live model calls and started no trial hosts.

**Scope and context controls: current increment and remaining work**

Scope boundaries precede richer handovers. The repository-task path now supplies a
fixed task contract and campaign-bound write scope. Its runtime implementation gives
executors declared source/test write roots plus scratch, and verifiers read-only
candidates plus scratch; it also denies access to archived private task assets and
audits candidate changes. The affected runtime crate passed 104 tests and four subsequent
focused context-bound regressions; final release formatting/build remains pending.
Separate threads and approved plan hashes alone do not establish semantic scope.
A generated plan or handover cannot widen the contract. The remaining context-budget
and retrieval work below is still proposed and must not be inferred from these scope changes.

Research/planning may inspect the repository. Implementation receives write access
only to declared task paths plus separate build/test scratch directories; enforce
that through the sandbox rather than shell-command guessing. Verification reads
the candidate implementation and writes exploratory tests/artifacts in scratch.
Repairs return to an executor under the same task contract. Before recording a
candidate, audit changed paths and independently check stated behavioral exclusions.
Filesystem checks cannot prove semantic scope, so report that distinction.

When a worker needs work outside the contract, record `scope_blocked` and end that
trial, then admit the next queued trial. Do not expand scope, rewrite the goal or
open a per-trial permission prompt. Count such outcomes when assessing usefulness.
Validate allowed changes, denied out-of-scope writes, symlink/rename containment,
read-only candidate verification, and failed-recording behavior in real-sandbox
mock tests. Keep all arms under the same scope rules.

Correct the interpretation of the existing size controls before changing them:

| Existing control | Meaning |
| --- | --- |
| Model catalog: 8,192-byte truncation budget | Budget used when presenting tool output; individual tool formatting also applies. It is not the whole model context. |
| Phase inputs: 8 KiB each, 16 KiB combined | Separate bounds on role instructions and the initial phase prompt. Oversized inputs are rejected. Later conversation/tool context is separate. |
| Research prompt: at most 2,500 characters | Instruction to compress research findings, rather than a measured model capacity. |
| Command-receipt preview: 8,192 bytes | Independent preview control. The recent fix preserves command identity when the preview is omitted. |
| Model profile: 1,048,576 tokens | Configured total context window; this does not establish useful capacity on every task. |

Make phase input and tool-output budgets separately versioned and recorded. Do
not raise all constants together or couple them to report-schema/receipt limits.
Retain long logs as protected artifacts with clear truncation markers and bounded
range retrieval. Apply byte and token bounds to injected content, following the
repository's context-size requirements. Larger evidence access never changes a
worker's write permissions. Calibration should demonstrate that relevant failures
beyond the initial output excerpt can still be retrieved.

**2. Introduce a versioned task interface and a varied task library**

Current implementation: [the registry](experiments/task_registry.py),
[independent evaluator](experiments/evaluate_task.py),
[calibration CLI](experiments/task_library.py), and campaign adapter cover 20
synthetic repository tasks: 12 Python, eight Rust, five per family, with 149 private
cases and two mutants per task. All are in the study split. Final shared calibration
passed: 20 references accepted, 20 starters and 40 mutants rejected, zero model calls.
Evidence paths are in [TASK_LIBRARY.md](TASK_LIBRARY.md); earlier language-local
self-checks are not the final acceptance record.
Four development tasks and eight confirmation tasks remain unimplemented. The
selection guidance below describes the broader intended collection, not extra assets
already present. See [TASK_LIBRARY.md](TASK_LIBRARY.md) for every actual assignment.

Replace the hard-coded choice between three function fixtures and the queue
fixture with an explicit task registry. Preserve adapters for those existing
fixtures as calibration coverage. Add repository-test adapters for Python and
Rust so the main study includes different languages, new builds and changes to
existing code. The user's required mix includes greenfield coding, extensions
and bug fixes; report these separately rather than treating all coding as one task.

Each task manifest records a task/version ID, task family, size band, capability
tags, language, repository snapshot and baseline commit, instruction text, fixed
scope contract, dependency/
toolchain pins, public checks, private evaluator identity, resource limits and
development/study/confirmation membership. Public task files and private grader assets have separate
inventories. Candidate code never receives reference patches or private tests.

The task interface has three responsibilities: create a clean checkout, describe
the agent-visible task, and independently evaluate a safely stopped candidate.
Adapters return the same result schema. They execute declared argument arrays
through the existing sandbox rather than interpolating task text into shell code.
Rust evaluation needs pinned, offline dependencies, an isolated writable build
directory and task-specific time limits; it must not trigger a full Codex workspace
test run. Candidate-controlled build scripts remain sandboxed.

Build the main collection in small task packs:

| Family | Main-study tasks | Example assignments and success criteria |
| --- | ---: | --- |
| Greenfield builds | 5 | Build a file-indexing CLI, a local HTTP booking service or a data importer from a minimal scaffold. Deliver the specified working interfaces, validation and persistence where required. |
| Extensions to existing code | 5 | Add pagination/filtering to an API, a new format to an importer or cancellation to a job runner. New behavior must work while existing callers and tests remain compatible. |
| Bug fixes | 5 | Diagnose and fix configuration precedence, duplicate event processing or corrupted state after interrupted writes. Resolve the reproduced defect and preserve surrounding behavior. |
| Refactoring and maintenance | 5 | Split a coupled module, replace a storage implementation or remove repeated parsing work. Preserve public behavior and meet a measurable structural or performance requirement. |

Target three Python and two Rust tasks per family: twenty tasks in total. These
are distinct assignments. Within each family include two small, two medium and
one larger bounded task. Assign size bands before model runs using integration
surface and required behaviors; calibrate resource limits on development tasks.
Do not define difficulty using which model happens to pass.

Spread capability tags across families: CLI/API design, parsing and data handling,
filesystem operations, persistence, concurrency and changes across modules. State
and concurrency are capabilities exercised by several kinds of task, rather than
a substitute for greenfield work. Avoid filling a family with minor variations
of one problem. The examples above are selection candidates, not implemented or
validated fixtures.

Greenfield tasks start from a pinned minimal scaffold with dependencies and test
entry points, without an existing solution. Specify observable behavior and a
finite deliverable while leaving implementation choices open. Permit new files
inside declared source/test directories; keep task authority and private grading
outside those writable directories. A greenfield assignment must not become an
open-ended request to keep inventing product features.

Extensions and fixes start from a functioning repository with existing tests and
documented compatibility requirements. Bug tasks provide symptoms or a public
reproducer without identifying the faulty implementation; private checks exercise
the cause and neighboring cases. Refactoring tasks need an explicit observable
requirement beyond an agent's opinion that the code is cleaner. Performance tasks
need a pinned workload and a repeatable measurement with calibrated tolerance.

Use multiple independent repository snapshots and record common repository ancestry
so related tasks are not presented as independent projects. Prefer realistic,
bounded assignments with clear contracts. Extracted examples must retain enough
surrounding code and regression tests to exercise integration. Check provenance
and dependency availability when selecting each task.

Use four separate development tasks for live smoke testing, one per family.
Reserve eight further tasks for confirmation, two per family; keep them out of
instruction tuning and initial ranking. Keep repository/project ancestry within
one split so close relatives cannot leak from development into confirmation.
The existing four diagnostic fixtures can validate adapters without joining the
new main-study scores.

For every task, check that a trusted solution passes, the starting implementation
or greenfield scaffold fails the intended new behavior, and at least two plausible
wrong solutions are rejected. A refactor task whose baseline already meets behavioral checks needs an
explicit, independently checkable structural requirement. Validate accepted output
equivalences against the written contract. Freeze the grader before model trials;
any later correction gets a new version and a separately labelled audit.

Acceptance: the runner can add a task by adding its manifest/assets without editing
the scheduler. Both language adapters produce comparable results, detect known
regressions, protect private grading material and leave candidate snapshots intact.

**3. Define understandable workflow conditions and measure their execution**

Current implementation: [repository-v1.toml](workflows/repository-v1.toml) defines
`repository-v1` and `repository-repair-v1`, sharing generic repository roles and
Markdown plans with maximum repairs 0 and 1 respectively. The four handover
conditions below are a future matrix; richer handover payloads and their comparative
measurement are not implemented by the current task-library increment.

Add generic, versioned research/planner/executor/verifier instructions, removing
queue-specific assumptions. Keep the same separate phase threads, role instructions,
scope contract, tools, renderer and model settings in all four initial conditions.
Every executor gets a bounded assignment. Both handover formats include the full
task contract and acceptance criteria; the compact arm must not omit authority.

| Condition ID | Information passed between phases | Maximum repair rounds |
| --- | --- | ---: |
| `compact-handover` | Task contract, plan and concise phase findings | 0 |
| `evidence-handover` | The same contract/plan plus a bounded file map, decisions, check evidence and unresolved issues | 0 |
| `compact-handover-repair` | Task contract, plan and concise phase findings | 1 |
| `evidence-handover-repair` | The same contract/plan plus a bounded file map, decisions, check evidence and unresolved issues | 1 |

Add a versioned handover policy alongside the existing role selectors and
`max_repairs` setting. Construct both views from the same categories of recorded
phase artifacts, preserve uncertainty and provenance, and record actual content
and size. Additional context is evidence, not new instructions or authority.
Keep the tool-output policy fixed across this first matrix so it is not confounded
with handover changes. Set explicit handover bounds during calibration and freeze
them before study tasks run. Larger caps alone do not demonstrate richer content.

A repair begins only
after a valid failed verification. Malformed reports, missing receipts, provider
errors and exhausted limits remain separately classified failures. All arms use
delegated plan decisions, zero automatic amendments and zero replacement trials.
Each trial generates a fresh plan under the same planner instructions. This is an
end-to-end workflow comparison, not a shared-plan experiment.

Reuse command receipts and candidate checkpoints for both outcome and scope
auditing. Give every arm the same lab-level public-test helper, recording command,
result, sequence and code/test hashes. Record handover omissions, truncation,
retrievals and rejected scope changes. Evidence that an agent followed a procedure
is separate from its assigned condition; ambiguous observations remain unknown.
Keep every started trial in its original condition for the main comparison.

Acceptance: real-host mock tests show distinct recorded handover contents, intact
task authority in both arms, recovery of longer test output, denied scope expansion,
read-only verification, and repair under the unchanged contract. Both repair limits
and the queue's no-prompt behavior must hold with stdin closed.

**4. Extend the queue into a study runner**

Current increment extends the existing freezer with task-library/split, pinned
toolchain, and `--task-just` selection. The just executable is frozen in the archive's
`task-tools/` directory; only that helper directory becomes readable to workers.
The Windows launcher `C:/Users/james/.codex-lab/queue-varied-tasks.ps1` defaults to
20 tasks × two generic workflows × five repetitions = 200 trials, `jobs=8`, `max_amendments=0`, and uses
`-PrepareOnly` for offline freezing or `-Execute <Linuxcampaign.json>` for an existing
freeze. Final task calibration passed; its evidence paths and the still-pending bundle/preparation are recorded
in [TASK_LIBRARY.md](TASK_LIBRARY.md). No live launch is included. The following randomized 240-trial
handover study, additional deadline/reporting controls, and study-specific interface
remain a roadmap, not claims about this preparation.

Add a study manifest above the existing workflow catalog. It selects a task suite,
named conditions, repetitions, a scheduling seed, concurrency, runtime limits and
the provider profile. The freezer expands it to an immutable list of trials and
pins task, evaluator, instruction, runtime and provider inputs. Preserve support
for existing campaign manifests rather than silently reinterpreting them.

For the first main study, expand twenty tasks by four conditions by three attempts:
240 trials, with at most sixteen active model hosts. Randomize condition order
within task/repetition groups using the recorded seed, and interleave groups.
The seed controls scheduling; it does not make model sampling deterministic.
Every trial starts from its own clean checkout and has its own run and policy IDs.

Add a common thirty-minute total model-host deadline per trial, including provider
waiting, while retaining the existing phase shutdown rules. Repair uses the
remaining trial allowance. Record queue waiting, model-host duration and grader
duration separately. Use a separate small evaluator pool with a recorded limit so
grading does not consume model-host slots. Account for shared machine contention
when interpreting timing comparisons.

Preserve cancellation behavior: stop admitting new trials and drain active work.
For a host deadline, request normal cancellation and retain terminal shutdown
evidence. If shutdown cannot be established, quarantine that checkout and mark its
evaluation unavailable. Do not run a grader against a potentially active writer.
Make preflight, setup and evaluator waits bounded too.

The launcher accepts one study configuration and exposes a readable progress
summary: queued, running, finished, correct, failed and unavailable. Individual
failures never open a micro-approval prompt. A coordinator interruption must retain
all started IDs and receipts. Reconciliation may admit never-started trials only
after checking process ownership; interrupted trials are retained, not silently
rerun. Document Windows/WSL lifetime requirements explicitly.

Time, concurrency and trial-count limits are not a hard dollar/token cap. Record
actual input, cached input and output usage, keeping missing usage unknown. Do not
claim equal compute from equal deadlines. Estimate a full campaign's usage range
from the live smoke run before launch; dollar estimates require verified prices.

Acceptance: an offline simulated 240-trial queue obeys admission limits, retains
failures, handles missing graders and deadlines, and cannot duplicate a started
trial. Freeze is reproducible for a given source/configuration/scheduling seed,
apart from explicitly recorded generated identities. Starting the runner with
stdin closed exercises every initial condition without an approval handoff.

**5. Produce a report that supports a decision**

Extend `terminal_run.py` and add separate result normalization and comparison
modules. Keep report generation independent of model execution so reports can be
regenerated from frozen artifacts. Emit versioned JSON, a plain-English Markdown
report and a local HTML view with condition/task filters and evidence links.

| Measure | Definition |
| --- | --- |
| Correctness | Independent task requirements pass and fixed regression checks remain passing. |
| Autonomous delivery | Correctness plus a completed workflow with zero human intervention. |
| False success | A valid final verifier pass whose finished candidate fails independent grading. |
| Repair benefit | Independent correctness before the repair versus after it, including regressions introduced by repair. |
| Usage per correct result | Usage for all started trials divided by correct results; unavailable if required usage is missing. |
| Reliability | Model/task, workflow/protocol, provider, timeout and evaluator failures shown separately. |
| Scope | Attempts to exceed allowed writes, scope-blocked outcomes and independently detected violations of stated exclusions. |
| Context delivery | Exact handover sizes/content, truncation and retrieval observations; distinguish available evidence from claims that the model used it. |

Grade immutable checkpoints from before any repair and after the final phase,
only after the host stops. These checkpoint grades never feed back into the
model. In-workflow repair receives public tests and verifier findings only. Candidate
implementation is read-only during verification; scratch tests are separately
recorded and cannot masquerade as changes to the delivered implementation.

Count planned, admitted, graded and correct trials explicitly. Unknown grading
does not become a task failure or a pass; incomplete campaigns are visibly
incomplete. Report an all-started autonomous-success rate, a graded-only task pass
rate with its denominator, and missing outcomes alongside both.

Show per-task and per-family results, the effect of evidence-rich handovers, the effect of
repair, and whether their combination behaves differently. Show differences by
size band where the sample supports them. A workflow
that helps greenfield construction but hurts bug diagnosis must be visible in
the report; an overall average alone is insufficient. Compare matched tasks
and resample complete task groups for exploratory uncertainty intervals, preserving
their conditions and repetitions; account for shared repositories where feasible.
Three attempts on twenty tasks is an initial screen. Neither repeated attempts
nor several tasks from one repository create broad evidence about all coding work.

A result is useful when it shows a repeatable gain in independent correctness or
autonomous delivery together with its usage/time tradeoff. Present inconclusive
results honestly. Before selecting a default, lock the candidate workflow and test
it against the baseline on the reserved confirmation tasks. Predeclare any
acceptable cost increase before examining those confirmation outcomes.

Acceptance: synthetic complete and incomplete campaigns verify denominators,
false-success classification, repair gains/regressions, missing usage and paired
comparisons. Cached input is never added a second time to total input. Evidence
links resolve and a reader can trace any aggregate failure back to its trial.

**6. Release the first useful study in stages**

| Stage | Work delivered | Evidence required before advancing |
| --- | --- | --- |
| Integration — complete | New versioned unattended host with latest fixes and limited provider profile | 36 selected Rust tests, 27 unique Python tests and a 200-trial offline package check passed; see the integration receipt. |
| Scope controls — runtime tested, release build pending | Fixed task authority, bounded executor writes, read-only verification and candidate audits | 104 affected-crate tests and four subsequent context-bound regressions passed; richer context policies and long-evidence retrieval remain future work. |
| Task interface — calibrated | 20 Python/Rust synthetic tasks, 149 private cases, legacy selection retained | All 80 expected starter/reference/mutant outcomes matched in the shared sandbox, with zero model calls. |
| Initial conditions — implemented | Two generic repository workflows, maximum repairs 0/1 | Final runtime validation under the same task authority. |
| Offline preparation — pending | 20 tasks × two workflows × five repetitions = 200 entries | Frozen inputs and prepare-only receipt; no model calls or live launch. |
| Handover conditions — proposed | Four handover/repair workflows with separate agents | Real-host mocked context, scope and repair coverage. |
| Broader study runner — proposed | Frozen randomized 240-trial expansion, bounded scheduling and progress | Offline queue, cancellation, deadline and duplicate-admission coverage. |
| Report | Correctness, reliability, usage and paired comparisons | Synthetic-result tests and verified local evidence links. |
| Live calibration — proposed | Four development tasks across four conditions, one attempt each: 16 live trials; tasks not yet created | End-to-end evidence is sound; grader/protocol defects are resolved in a newly versioned release if found. |
| Broader main study — proposed | Twenty tasks across four handover conditions and three attempts: 240 live trials | Frozen inputs, calibrated graders, validated bundle and a recorded usage estimate. |
| Confirmation — proposed | Eight reserved tasks, baseline versus one selected workflow, three attempts: 48 trials; tasks not yet created | Candidate and acceptance rule fixed before reading confirmation outcomes. |

Implement the task packs alongside the runner/report stages locally. Split code
into reviewable changes, normally below the repository's 800-line guidance and
smaller for complex runtime logic. Start with the smallest relevant tests using
`just test`; run scoped `just fix` where needed and `just fmt`/`just fmt-check`
afterward, with no test rerun after formatting and no full workspace suite. Python
tests cover the scheduler, grading and reports; real-host mock tests cover actual
phase transitions and shutdown.

The plan covers preparation and implementation of these stages. The main and
confirmation campaigns are distinct launches with their own frozen configuration;
neither is started by writing this plan. Once a finite campaign is selected for
execution, delegated decisions handle its plans and steps without further human
review prompts. The four development tasks and old diagnostic fixtures never
enter the main-study ranking.

**7. Add further architecture experiments on the same foundation**

| Extension | Concrete implementation | Controlled study |
| --- | --- | --- |
| Verifier quality | Add a verifier-only campaign mode around `VerificationInput`, with fresh delegated authority and explicit provenance for curated inputs. Mount candidate implementation read-only; allow new tests only in scratch space. | Give every verifier the exact same new clean and deliberately faulty candidates, plans and implementation evidence. Measure defect detection, false alarms, report validity and usage. |
| Tool-output policies | Extend the initial separate size controls with versioned excerpt/retrieval policies. Preserve full artifacts and record actual tool limits. | Compare the current 8 KiB budget with larger budgets or more selective output, holding phase handovers and scope fixed. Measure missed evidence, successful retrieval, correctness and usage. |
| Automatic test feedback | Add a policy for the trusted public-test helper after defined change checkpoints. Record host checks separately from agent-requested checks. | Compare agent-selected testing with enforced public feedback under the same workflow. Private grading remains out of the loop. |
| Model allocation | Freeze a validated model/provider profile per phase and record actual selections and usage. | Compare a single model with a different reviewer or a different allocation of computation, using the same task suite. |
| Coding procedures | Add tests-first and implementation-first role variants once context and scope controls are established. Observe failing-test/passing-test evidence rather than relying on instruction labels. | Compare coding methods under the selected separate-agent architecture and fixed recovery policy. |

These settings belong in versioned lab configuration and effective-setting
evidence. Unselected settings preserve current behavior. Add them one at a time;
the initial 240-trial experiment does not depend on implementing every extension.
Verifier-only trials need an explicit extension of campaign dispatch: the current
unattended worker always runs the complete workflow. Curated implementation
evidence must not be presented as a historical model run that never happened.

The task manifest, independent grading and comparison report are reusable across
these extensions. Each new experiment should name the practical decision it is
meant to settle before choosing variants or spending the campaign budget.

**Implementation map and references**

- Existing queue/input work: [campaign_inputs.py](experiments/campaign_inputs.py),
  [run_campaign.py](experiments/run_campaign.py), [UNATTENDED.md](UNATTENDED.md).
- Workflow fields and runtime decisions: [config.rs](../codex-rs/lab/src/config.rs),
  [campaign.rs](../codex-rs/lab-runtime/src/campaign.rs),
  [driver.rs](../codex-rs/lab-runtime/src/driver.rs).
- Current context limits: [context.rs](../codex-rs/lab-runtime/src/context.rs),
  [model profile](providers/muse-contributor.models.json). Scope enforcement starts
  at [authority.rs](../codex-rs/lab-runtime/src/authority.rs) and the runtime sandbox
  policy; new per-task write restrictions require implementation.
- Task/evaluator adapters: [fixture_registry.py](experiments/fixture_registry.py),
  [evaluate_fixture.py](experiments/evaluate_fixture.py),
  [evaluate_queue.py](experiments/evaluate_queue.py).
- Evidence and replay: [terminal_run.py](experiments/terminal_run.py),
  [git_evidence.rs](../codex-rs/lab-runtime/src/git_evidence.rs),
  [verification_input.rs](../codex-rs/lab-runtime/src/verification_input.rs).
- New logical modules: task manifests/registry adapters; study manifest/freezer;
  procedural evidence; deadline/cancellation policy; result normalization;
  study comparison/report. Keep these separate from the already substantial runner.
- Experimental method: [NIST randomized block designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm)
  and [Anthropic's agent-evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
