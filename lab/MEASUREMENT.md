# Measuring failures and preparing varied tasks

The evaluator can now measure both `completed` and `failed` workflows. It checks sequential phase/dispatch records, matching session/checkout identity and every phase's shutdown artifact while holding the existing repository launch lock. Active runs, missing shutdown evidence and wrong repositories are rejected. Failed workflows remain failed even if their code passes independent tests.

Each new evaluation writes `observation.json` (available usage, phase/tool counts, approval/edit/amendment observations and Git metadata), `candidate.diff`, and `evaluation.json`. Source journals are read-only. Missing token usage and unscored plan deviations remain null. This is an external observer; it neither repairs host metrics nor resumes a session.

## Reevaluate an older run

The evaluator still pins its implementation by default. To deliberately measure an old candidate with a changed evaluator, supply the **current** evaluator digest explicitly and use a new output directory. The report retains both the original fixture evaluator digest and the digest actually used. Task/interpreter/baseline checks remain mandatory. This does not change any old result or make old/new evaluations identical controls.

```sh
python3.12 lab/experiments/evaluate_fixture.py \
  --repository /absolute/fixture/repository \
  --fixture-manifest /absolute/fixture/fixture.json \
  --sandbox /absolute/codex-linux-sandbox \
  --run /absolute/runs/execution \
  --evaluator-sha256 CURRENT_EVALUATOR_SHA256 \
  --output /absolute/new-evaluation
```

The digest is returned by `setup_fixture.evaluator_fingerprint(FIXTURE_NAME)` in `lab/experiments`. The existing upstream sandbox alias and Linux/Python 3.12 requirements are unchanged.

## Three tasks, one pair each

| Task | Primary behavior | Independent API / CLI cases | Fixed public tests |
| --- | --- | --- | --- |
| `csv-summary-v1` | CSV grammar, text preservation, CLI output | 21 / 21 | 3 |
| `dependency-order-v1` | Dependency validity, cycles, deterministic available-task ordering | 14 / 14 | 3 |
| `config-merge-v1` | Recursive precedence, replacement semantics, input preservation | 14 / 14 | 3 |

Expected answers and calibration references stay outside the model checkout. API observations detect input mutation. All tasks use stdlib Python and small repositories; they span different behaviors but are not representative of general production coding.

```sh
python3.12 lab/experiments/setup_suite.py setup /absolute/suite \
  --binary /absolute/codex-lab --codex-home /absolute/dedicated-home

# Supply the configured provider credential through the environment, never argv.
python3.12 /absolute/suite/inputs/lab/experiments/setup_suite.py \
  prepare /absolute/suite --task dependency-order-v1
```

Repeat preparation for the other two explicit task names. Setup creates separate checkouts and freezes copies of task/evaluator/workflow/instruction sources, plus hashes of the runtime binaries, interpreter and provider configuration/catalog. Preparation validates pins, generates one canonical plan using the existing Markdown profile, imports it into JSON, and exits with `tasks/TASK/review.json`. Stdin is closed; this coordinator cannot approve or implement tasks. Existing `run-prepared` handles each later execution's real human decision.

`suite.json` prespecifies one execution attempt per condition and alternates condition order by task. Do not retry failures automatically or substitute successful retries into the result set. An amendment requires a fresh decision and is reported as a changed condition. Six planned executions share the existing runtime/context limits and selected model configuration; there is **no new hard cumulative token or spend limiter**. These recorded caps are not a promise of equal actual token consumption.

Report every outcome: workflow completion, independently evaluated task success, test counts, usage and missing data. Existing Rust `compare` remains conservative about failed runs and missing original host metrics, returning descriptive results for such pairs. External observations do not manufacture those original artifacts. One pair per task has no useful statistical power for choosing a winner; its purpose is to test measurement and identify workflow failure modes before broader evaluation.

Development authorization, exact scope and handoff state are recorded in [MEASUREMENT_PLAN.md](MEASUREMENT_PLAN.md), [measurement-plan.json](measurement-plan.json) and [PROGRESS.md](PROGRESS.md). Each new live implementation plan still requires separate human approval.
