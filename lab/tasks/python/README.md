# Python study task fixtures

Twelve independent, standard-library-only Python 3.12 CLI projects, all in the study split.
Each family has one small, medium, and large task; task and project IDs are distinct.
Only project/ and TASK.md are candidate-facing. solution/, mutants/, and private/ stay host-side.
Each mutant overlays the solution and changes one plausible implementation decision.

| Family | Small | Medium | Large |
|---|---|---|---|
| Greenfield | py-log-tally: Unicode token frequencies | py-dependency-waves: dependency graph scheduling | py-document-index: recursive persistent text index |
| Extension | py-csv-rollup: grouped integer CSV totals | py-room-calendar: atomic booking replacement | py-ledger-batches: atomic idempotent transfers |
| Bug fix | py-semver-order: numeric prerelease precedence | py-csv-multiset: duplicate-aware record reconciliation | py-route-planner: directed cheapest paths and canonical ties |
| Maintenance | py-snapshot-format: canonical v2 migration | py-durable-queue: interrupted-tail recovery | py-batch-checksums: concurrent per-file fault isolation |

The public examples preserve existing behavior for non-greenfield projects. Private cases add
edge, regression, failure, persistence, and exact-byte checks; they are never copied into candidates.
Maintenance criteria are measurable compatibility/reliability requirements, not subjective style.
All commands accept data paths relative to their working directory. src/ and tests/ are the only
writable candidate paths. pyproject.toml and .python-version pin the project contract to Python 3.12.

Validation status is recorded in VALIDATION.json after host-only self-calibration. That report is
fixture calibration, not live-model performance, and does not modify historical experiment runs.

The initial Python 3.12.6 self-check passed all 12 solution public suites and the then-current 80 private cases. All 12
baselines fail required acceptance behavior, all 24 mutants fail private cases, and all 9 existing
non-greenfield baseline public suites pass. The host self-check applies overlays to temporary
repositories and runs each private case in separate temporary storage, with steps sharing that
case's storage. It preserves and compares file bytes, including deliberate CRLF fixtures. Sandbox
isolation and frozen-test enforcement are the separate shared evaluator's responsibility.

Contract review subsequently added two repeated-ID invalid-amount ledger regressions (82 private
cases total) and corrected receipt validation in the reference and mutant overlays. The recorded
self-check predates those changes. Final shared Linux/WSL calibration subsequently accepted all 12
references and rejected all 12 starters and 24 mutants (`calibrated=true`, 48 variants, zero model
calls). Its current acceptance record is
`/home/james/.cache/codex-lab-task-calibration/python-final-v1-20260907/calibration.json`.

The checksum task starts with a concurrent worker pool, but its acceptance checks measure ordered
results and isolation of individual file failures. Parallel execution and worker count are not graded.
