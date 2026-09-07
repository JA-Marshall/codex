# Unattended experiment campaigns

Choose the tasks, workflows, repetition count and concurrency once. The campaign
runner creates fresh isolated trials, generates each plan, delegates its approval,
executes the work and independently evaluates the result. A failure is retained as
an outcome; it does not stop unrelated trials or wait for a terminal answer.

This mode implements the user's request to stop babysitting each new plan and
queue hundreds of experiments. Earlier interactive campaigns and their frozen
approvals retain their original meaning.

## Queue and execution

On this Windows installation, the local launcher is
`C:\Users\james\.codex-lab\queue-trials.ps1`:

```powershell
& C:\Users\james\.codex-lab\queue-trials.ps1 -Trials 200 -Jobs 16
```

This starts 200 fresh durable-queue trials using `queue-baa-v2`. Change `-Workflow`
or `-Fixture` to select another supported condition. `-MaxAmendments 2` permits up
to two automatic plan revisions. `-PrepareOnly` freezes the batch without model
calls. The launcher loads the existing provider credential privately, selects the
versioned unattended binary, and creates a new timestamped output directory.
It runs in the current terminal; keep that terminal and WSL running until it ends.

The integrated release uses the shared Muse request limiter and the separate
`muse-contributor-unattended-v2` provider home. Its model instructions describe
delegated host authorization; other model and provider settings follow the limited
profile. Historical profiles and frozen batches retain their original settings.
The installed bundle is
`/home/james/.cache/codex-lab-binaries/unattended-v2-20260907`.
This local convenience wrapper is separate from the portable Python entry point.

The queue holds up to 1,000 trials with 1–32 active trial workers. A slot covers
fixture setup, the model host and independent evaluation, so hundreds of queued
trials do not become hundreds of live hosts. The default concurrency is 16.
Every fixture/workflow/repetition combination receives a fresh checkout and run
ID. Plans are independently generated for each trial; this is not shared-plan or
fixed-candidate pairing.

Use the versioned `codex-lab` binary built with campaign support, its accompanying
sandbox resources, and Python 3.12 in the existing Linux/WSL environment. The
dedicated provider home and credentials follow [RUNNING.md](RUNNING.md).

The entry point is `lab/experiments/run_campaign.py`. Its `--help` lists the binary,
provider home, catalog, instruction root, evaluator sandbox and output arguments.
Muse campaigns also require `--provider-service` pointing to the existing shared
proxy's `service.json`. The freezer checks the selected provider URL and pins the
service receipt and both service source files. It does not make a health or model
request. Execution checks local health and the configured request allowance before
admitting workers and before each model host starts. An unavailable service stops
execution without a direct-provider fallback. Other provider models may omit this
Muse-specific argument. The service receipt records setup identity; a health check
does not attest the code running inside the service process.
Repeat `--fixture` and `--workflow` to select combinations; `--repetitions 200` on
one fixture and one workflow queues 200 trials. `--jobs 16` runs at most 16 at once.

`--prepare-only` freezes an offline campaign and prints the command that executes
it later. It makes no model calls. Normal invocation freezes the same inputs and
executes the frozen runner without an intervening plan-review handoff. The
campaign output directory must be new. Keep it outside candidate repositories.

## Delegated decisions

The frozen campaign catalog explicitly selects `approval = "campaign_delegated"`.
The runtime also requires a per-trial `--campaign-policy` file outside the writable
candidate repository. That policy binds the campaign/run ID, repository and base
commit, original task digest, workflow selector and catalog digest. The runtime
copies its exact bytes to protected evidence before any model phase.

Each accepted plan has its own exact target and a `delegated_approved` event
containing the policy digest. Automated decisions are not described as fresh human
reviews. The original terminal/JSON review entry points remain interactive.

By default `--max-amendments 0` stops a trial that asks to revise its plan and the
queue continues. A finite value up to four allows that many revisions without
asking the operator. The task and independent evaluator stay fixed. This bound
does not mean the host can judge whether revised plan text is semantically sound.
Ordinary verify/repair cycles use the selected workflow's existing `max_repairs`;
they do not reset the amendment allowance. Whole-trial failures are not silently
retried or replaced.

Sandbox, tool restrictions, phase shutdown, receipts and independent grading still
apply. A finished workflow and a passing implementation are reported separately.
Evaluation failures remain separate from model/workflow failures too.

## Results and stopping

The campaign preserves its input snapshots, policy files, event log, per-trial
logs, candidate artifacts and evaluation output. Its final result includes every
queued trial, including failures and trials that were never admitted.

Cancellation stops new admissions and drains already running trials. There is no
automatic crash resume or approval replay. An interrupted output directory must
not be reused as a new campaign; inspect its existing processes and records first.

Trial count, concurrency, amendment limits and existing phase/repair bounds are
finite controls. They are not a hard token or dollar limit. Token usage is reported
where host evidence is available, with missing usage kept distinct from zero.

Unattended campaigns alter approval procedure and scheduling. Label that change
when comparing them with earlier human-reviewed or shared-plan results.

## Validation

The integrated release's validation is recorded separately in
[unattended-integration-2026-09-07.json](unattended-integration-2026-09-07.json).

The [validation receipt](unattended-validation-2026-09-07.json) records 32 focused
Rust tests and 16 Python tests, including a real mock-provider CLI run with stdin
closed, 100 fake subprocess trials at three concurrent workers, independent
evaluation after a failed host, and a 200-trial offline preparation. Scoped strict
Clippy, formatting and the packaged binary help check passed. No live provider
calls or full workspace test suite were used for this feature.
