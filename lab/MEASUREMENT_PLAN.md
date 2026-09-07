# Failure measurement and varied-task comparison

Approved scope: the user's “Go” after the proposal to measure failed runs, then compare the existing Markdown/JSON workflows on a small varied task set. The canonical source is `measurement-plan.json`; live task plans still require separate exact human decisions.

## Actual extension points

`lab-runtime/src/backend.rs::PhaseOutput` guarantees upstream shutdown on success and retains shutdown events. `authority.rs` records sequential phase starts/stops. `driver_preparation.rs::finish_run` currently omits final metrics/diff on errors. We can recover available observations externally without changing this driver or restoring authority.

`lab/experiments/evaluate_fixture.py` already holds the Git metadata launch lock, isolates candidate execution through upstream Linux permissions, bounds output/time, and checks evaluator/interpreter/baseline fingerprints. Extend that boundary to admit completed **or failed** terminal runs only when every started phase has a matching shutdown receipt and phase artifact. Unknown shutdown remains ineligible. Store separate observations beside the new evaluation, leaving source journals intact.

`setup_fixture.py`, `evaluation_worker.py`, and `fixture_cases.py` currently assume CSV. Add an explicit three-entry task registry and select task-specific public tests/API inputs through it. Preserve the default CSV entry point. Add dependency ordering and layered-configuration fixtures; independently authored expected answers and calibration references stay outside candidate repositories.

Use existing `prepare`, `run-prepared`, and `compare` commands. A small manifest records one pair per task, deterministic alternating execution order, exact frozen inputs and the current context/runtime limits. No new scheduler or runtime policy interface is needed. Existing comparison conservatively calls failed pairs descriptive; retain that limitation instead of changing its classification rules during this iteration.

## Refined scope and critique

- Core changes/merge risk: no upstream core/provider/TUI/sandbox/auth changes; favor Python experiment modules. No new dependencies or Rust lifecycle changes.
- Coupling: keep current model, planner, executor, verifier and workflow profiles unchanged. Change only representation within each task pair. One canonical plan is generated once per task, then imported into its other condition.
- Reproducibility: new evaluations explicitly pin their evaluator revision. Reevaluating the old failed pilot must record that it uses a new evaluator; do not forge a new fixture manifest or replace the original report. Keep old outputs and run journals byte-identical.
- Budget: three tasks, one attempt per representation (six execution attempts), no automatic retries/amendment approvals. Record the existing 32-phase/run, 30-minute/phase, evidence and context caps, plus model context settings. There is no new hard cumulative token/spend limiter; do not describe recorded usage as such a limit.
- Premature abstractions deferred: general task plugins, sweeps, statistical rankings, new renderers, multiple-command verifier schema and runtime failure finalization. The task set is a diagnostic sample, not representative of general coding work.
- Reviewable stages: M01 terminal observation/evaluator safety; M02 two calibrated tasks/explicit selection; M03 frozen suite preparation and documentation. Each stage gets focused tests and a ledger entry before proceeding. No 17,000-test suite.

Acceptance: safely measure an existing failed candidate without rewriting its workflow; reject active/unknown-shutdown/drifted inputs; calibrate every task against baseline/no-op/incomplete/reference implementations; prepare three shared canonical plans and six exact review targets with identical within-pair controls. Live implementation waits for those separate approvals.
