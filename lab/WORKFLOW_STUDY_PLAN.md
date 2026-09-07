**Implementation plan: useful unattended workflow experiments**

Prepared 7 September 2026. Status: proposed implementation, grounded in the current
source. This document adds no runtime changes and launches no experiments.

The objective is to identify which working methods finish repository tasks
correctly, how much additional checking and repair costs, and how reliably those
methods work without human intervention. A plan is one input to that process.

**1. Integrate the working infrastructure into a new release**

The source currently has two relevant lines of development:

| Source | Available behavior | Integration required |
| --- | --- | --- |
| Main line at `1adda1a5c0` | Bounded repair, corrected evaluator, shared provider limiter, long-command receipt fix | Use as the integration base, rechecking HEAD when implementation starts. |
| `lab/unattended-campaign` at `f372358bfe` | Delegated plan decisions, frozen campaigns, bounded queue, independent grading of failed hosts | Port its feature commits onto the current base; its older repair corrections are already superseded. |
| Installed unattended launcher | Queues a finite campaign with no plan prompts | It still selects the direct provider home and an older binary. Replace its default only after validating a new versioned bundle. |

Create a dedicated integration worktree and separate build mirror. The user reports
that other work consists of running earlier tasks. Preserve their frozen binaries,
source snapshots, provider configuration and output directories. Use the existing
shared proxy; do not restart it or install a second limiter. All new model traffic
must use `muse-contributor-limited`, with a local health check and recorded service
identity. Record overlapping workload and provider waiting time where attributable.

Keep changes primarily in `codex-rs/lab`, `codex-rs/lab-runtime` and
`lab/experiments`. Continue using upstream execution, sandbox and model interfaces.
Retain the distinction between historical human approvals and explicitly delegated
new campaigns. The earlier experiment reset still applies: historical results are
debugging evidence and are excluded from new comparisons.

Acceptance: the integrated real host completes a mock-provider
research/plan/implement/fail/repair/pass run with stdin closed, including a command
longer than the old receipt preview limit. A second trial fails cleanly and the
queue continues. Local proxy tests demonstrate a shared allowance and no direct
provider fallback. Package a new binary and frozen scripts with source hashes.

**2. Introduce a versioned task interface and a varied task library**

Replace the hard-coded choice between three function fixtures and the queue
fixture with an explicit task registry. Preserve adapters for those existing
fixtures as calibration coverage. Add repository-test adapters for Python and
Rust so the main study includes different languages and changes to existing code.

Each task manifest records a task/version ID, task family, language, repository
snapshot and baseline commit, instruction text, dependency/toolchain pins, public
checks, private evaluator identity, resource limits and development/study/
confirmation membership. Public task files and private grader assets have separate
inventories. Candidate code never receives reference patches or private tests.

The task interface has three responsibilities: create a clean checkout, describe
the agent-visible task, and independently evaluate a safely stopped candidate.
Adapters return the same result schema. They execute declared argument arrays
through the existing sandbox rather than interpolating task text into shell code.
Rust evaluation needs pinned, offline dependencies, an isolated writable build
directory and task-specific time limits; it must not trigger a full Codex workspace
test run. Candidate-controlled build scripts remain sandboxed.

Build the main collection in small task packs:

| Family | Main-study tasks | Example behavior to assess |
| --- | ---: | --- |
| Existing bug fixes | 5 | Fix a parsing, precedence or boundary defect while preserving established behavior. |
| Feature additions | 5 | Extend a CLI or API, including validation and compatibility. |
| Changes across modules | 5 | Refactor or extend behavior spanning several files while retaining public contracts. |
| State and concurrency | 5 | Preserve persistence, transactions, cancellation, idempotency or competing-worker behavior. |

Target three Python and two Rust tasks per family: twenty tasks in total. These
are distinct repository changes, not twenty input cases for one queue problem.
Use multiple independent repository snapshots and record common repository ancestry
so related tasks are not presented as independent projects. Prefer bounded real
repository changes with clear contracts. Extracted examples must retain enough
surrounding code and regression tests to exercise integration. Check provenance
and dependency availability when selecting each task.

Use four separate development tasks for live smoke testing. Reserve eight further
tasks for confirmation; keep them out of instruction tuning and initial ranking.
The existing four diagnostic fixtures can validate adapters without joining the
new main-study scores.

For every task, check that a trusted solution passes, the starting implementation
fails the intended new behavior, and at least two plausible wrong solutions are
rejected. A refactor task whose baseline already meets behavioral checks needs an
explicit, independently checkable structural requirement. Validate accepted output
equivalences against the written contract. Freeze the grader before model trials;
any later correction gets a new version and a separately labelled audit.

Acceptance: the runner can add a task by adding its manifest/assets without editing
the scheduler. Both language adapters produce comparable results, detect known
regressions, protect private grading material and leave candidate snapshots intact.

**3. Define understandable workflow conditions and measure their execution**

Add generic, versioned executor instructions and a fixed generic planner/verifier.
Remove queue-specific assumptions from these new modules. The planner must permit
either implementation order: it should specify behavior and dependencies without
forcing all tests to the last step. Pin the same planner, verifier, renderer,
provider, model settings and available tools in all four initial conditions.

| Condition ID | Implementation method | Maximum repair rounds |
| --- | --- | ---: |
| `implementation-first` | Implement the behavior, then test it | 0 |
| `tests-first` | Demonstrate a relevant failing test, implement, then pass it | 0 |
| `implementation-first-repair` | Implement the behavior, then test it | 1 |
| `tests-first-repair` | Demonstrate a relevant failing test, implement, then pass it | 1 |

Use the existing role selectors and `max_repairs` setting. A repair begins only
after a valid failed verification. Malformed reports, missing receipts, provider
errors and exhausted limits remain separately classified failures. All arms use
delegated plan decisions, zero automatic amendments and zero replacement trials.
Each trial generates a fresh plan under the same planner instructions. This is an
end-to-end workflow comparison, not a shared-plan experiment.

Add bounded procedural evidence alongside outcome grading. Reuse command receipts
and candidate checkpoints. Give every arm the same lab-level public-test helper,
which records the command, result, sequence and code/test hashes. Preserve relevant
pre-change snapshots when a test-first cycle is attempted. The independent audit
checks that the same test fails for the intended behavior before implementation and
passes afterward without weakening it. Syntax/import failures alone are not a
successful test-first demonstration. Only supported, observed test invocations
receive that classification; ambiguous traces remain unknown.

Procedure classifications are `observed`, `not_observed` or `unknown`, with evidence
links. Do not manufacture compliance from the selected skill name or the model's
summary. Keep trials that did not follow their assigned instructions in their
original condition for the main comparison; report compliance separately.

Acceptance: mock traces distinguish a real failing-test/passing-test cycle from
tests added after implementation, a weakened assertion and missing evidence. Both
executor instructions are compatible with the fixed planner. Repair-disabled and
repair-enabled runs respect their frozen limits.

**4. Extend the queue into a study runner**

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
| Procedure | Evidence-backed adherence to the assigned implementation method. |

Grade immutable checkpoints from before any repair and after the final phase,
only after the host stops. These checkpoint grades never feed back into the
model. In-workflow repair receives public tests and verifier findings only. Record
edits made during verification separately so they cannot masquerade as executor
improvements or a nominally absent repair round.

Count planned, admitted, graded and correct trials explicitly. Unknown grading
does not become a task failure or a pass; incomplete campaigns are visibly
incomplete. Report an all-started autonomous-success rate, a graded-only task pass
rate with its denominator, and missing outcomes alongside both.

Show per-task and per-family results, the effect of tests-first, the effect of
repair, and whether their combination behaves differently. Compare matched tasks
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
| Integration | New versioned unattended host with latest fixes and limited provider profile | Focused domain/runtime and mock-proxy tests. |
| Task interface | Legacy adapters plus Python/Rust repository adapters | Trusted solutions pass; deliberately wrong solutions fail; sandbox and snapshot checks pass. |
| Conditions | Four generic workflows and procedural observations | Real-host mocked procedure and repair coverage. |
| Study runner | Frozen 240-trial expansion, bounded scheduling and progress | Offline queue, cancellation, deadline and duplicate-admission coverage. |
| Report | Correctness, reliability, usage and paired comparisons | Synthetic-result tests and verified local evidence links. |
| Calibration | Four development tasks across four conditions, one attempt each: 16 live trials | End-to-end evidence is sound; grader/protocol defects are resolved in a newly versioned release if found. |
| Main study | Twenty fresh tasks across four conditions and three attempts: 240 live trials | Frozen inputs, calibrated graders, validated bundle and a recorded usage estimate. |
| Confirmation | Eight reserved tasks, baseline versus one selected workflow, three attempts: 48 trials | Candidate and acceptance rule fixed before reading confirmation outcomes. |

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
| Context handovers | Add versioned handover policies to the workflow settings; construct and record bounded context in the lab runtime using existing interfaces. | Compare a short factual handover with fuller evidence while keeping candidate and available tools fixed. Measure final task outcomes and actual context usage. |
| Automatic test feedback | Add a policy for the trusted public-test helper after defined change checkpoints. Record host checks separately from agent-requested checks. | Compare agent-selected testing with enforced public feedback under the same workflow. Private grading remains out of the loop. |
| Model allocation | Freeze a validated model/provider profile per phase and record actual selections and usage. | Compare a single model with a different reviewer or a different allocation of computation, using the same task suite. |

These settings belong in versioned lab configuration and effective-setting
evidence. Unselected settings preserve current behavior. Add them one at a time;
the initial 240-trial experiment does not depend on implementing all four.
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
