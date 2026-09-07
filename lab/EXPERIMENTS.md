# Prepared review and the first comparison

The approved N01–N04 implementation adds isolated modules to `codex-rs/lab-runtime`. It makes no new changes to Codex core, its provider abstraction, tool dispatch, sandbox, authentication, TUI or session persistence. The source development plan remains [next-steps-plan.json](next-steps-plan.json); current evidence and outstanding live approvals are in [PROGRESS.md](PROGRESS.md).

## Durable human review

`codex-lab prepare` accepts the same task/provider/workflow options as the existing immediate host:

```sh
codex-lab prepare \
  --repository /absolute/task-repository --commit FULL_COMMIT \
  --codex-home /absolute/dedicated-home --runs-directory /absolute/runs \
  --run-id preparation-001 --task-file /absolute/task.txt \
  --workflow-catalog /absolute/codex/lab/workflows/foundation.toml \
  --instruction-root /absolute/codex/lab --workflow plan-md-v1

codex-lab run-prepared \
  --prepared /absolute/runs/preparation-001/evidence/prepared.json \
  --run-id execution-001
```

Preparation exits after upstream research/planning threads shut down, canonical plan validation succeeds, and both later phase prompts fit the existing context budget. Its workflow remains `awaiting_plan_approval`. It does not report task completion. `--plan-file` can import canonical JSON without calling the planner, and still grants no approval.

The final descriptor seals bounded artifacts and references the original run. A later launch verifies the descriptor and artifacts, re-resolves current provider/catalog/settings/binaries/roles and the repository baseline, then creates a fresh execution run. The exact source task/catalog bytes are intentionally frozen; editing their original input files does not modify the checkpoint. To change either, prepare again. Changes to current selected skills, runtime settings or repository baseline require new preparation.

The trusted terminal prints the canonical plan's selected view and a target containing the new run ID, plan identity/revision, content SHA-256 and run-spec SHA-256. Entering `approve <displayed-content-sha256>` is required before implementation. EOF, abort, rejection, a wrong digest or a failed write cannot approve. Human JSON edits create a new revision and another review. An implementation amendment uses the existing stop/shutdown/replan/review flow.

All launch modes hold an operating-system file lock in the repository's Git metadata directory, protected by the upstream sandbox's metadata policy. The same lock is used by evaluation. It prevents competing lab hosts, regardless of selected home or run directory. It does not lock unrelated editors; the host rechecks the initial baseline after human review, and the repository must otherwise be quiescent. The persistent lock file is never unlinked; process death releases its kernel lock. General session recovery and partial implementation resume remain unsupported.

`codex-lab run ...` and the historical flat `codex-lab --repository ...` invocation retain immediate review behavior. There is no automatic approval switch. Original prepared and failed journals are never reopened for writing. Preparation costs are recorded separately from child execution costs; parent lineage identifies the relationship.

## CSV fixture and independent evaluation

Use Linux with the pinned Python 3.12 interpreter and the existing `codex-linux-sandbox` dispatch alias for the built `codex-lab` binary. The interpreter must also be available as `python3.12` on the runtime's pinned tool PATH before starting a task.

```sh
python3.12 lab/experiments/setup_fixture.py /absolute/fixture-001
```

The new destination contains `repository/` and `fixture.json`. The checkout contains the task, an intentionally broken CSV API/CLI, and public tests. Its Git commit is deterministic. Setup records task/tree/file hashes, interpreter identity and the evaluator fingerprint. Hidden expected answers and the calibration reference stay outside the model checkout and prompt. They are local experiment inputs, not a secret benchmark service.

After the live workflow completes and shuts down:

```sh
python3.12 lab/experiments/evaluate_fixture.py \
  --repository /absolute/fixture-001/repository \
  --fixture-manifest /absolute/fixture-001/fixture.json \
  --sandbox /absolute/codex-linux-sandbox \
  --run /absolute/runs/execution-001 \
  --output /absolute/runs/execution-001/evaluation
```

The evaluator holds the launch lock, verifies the task/baseline/interpreter/evaluator identity, and runs observations through upstream managed permissions. Candidate files and fixed public tests are read-only; a separate scratch directory is writable. Expected answers and user homes are absent from the sandbox, networking is disabled, credentials are not inherited, and output/time are bounded. Isolation probes must pass first. The evaluator compares actual API/CLI observations, rather than accepting the model's verification claims. Candidate file hashes must remain unchanged throughout evaluation. A new output directory is required; existing reports are never overwritten.

Calibration demonstrates that the broken baseline, no-op and plausible incomplete fixes fail while the reference passes the 21 API and 21 CLI cases plus fixed public tests. The fixture is an integration pilot, not a representative coding benchmark.

## Recorded control comparison

```sh
codex-lab compare /absolute/runs/md-execution /absolute/runs/json-execution \
  --vary plan.renderer --output /absolute/comparison-001
```

The command reads bounded artifacts and writes JSON plus Markdown outside both source runs. It validates preparation lineage, canonical/rendered plans, actual instruction snapshots, model/settings fingerprints, completion/approval history and evaluator linkage. It compares all recorded settings and unknown additional control fields conservatively. Workflow names, inheritance provenance, role file locations and run identities are displayed as metadata differences; role content and effective behavior remain controls.

Only one differing control, `plan.renderer`, can receive `controlled_recorded_pair`. Missing controls, edits, amendments, unrelated differences and incomplete runs receive `descriptive_only`. Both labels concern recorded controls: remote immutable serving revisions and unrecorded system/provider state remain unknown. No winner or reliability estimate is inferred from one observation per condition.

For the live pilot, generate one canonical plan, prepare a Markdown condition and a JSON condition from those exact bytes, and obtain a distinct human approval for each execution. Fresh baseline checkouts and unchanged model/catalog/roles/settings are required. Live execution and comparison remain pending until those task-specific human decisions; development approval does not substitute for them.
