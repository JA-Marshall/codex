# Repository task library

The library contains 20 bounded synthetic coding assignments: 12 Python and eight Rust, with five
tasks in each of four families. Every family has two small, two medium, and one large task. All
20 tasks belong to the `study` split and have distinct project IDs. There are 149 private cases,
20 reference solutions, and 40 deliberately incorrect solution variants.

This implementation increment adds a varied task interface to the existing unattended runner and
two generic workflows differing only in their maximum repair rounds. Final shared Linux/WSL
sandbox calibration passed: all 80 variants matched their expected outcomes with zero model calls.
The frozen offline preparation contains **200 trials = 20 tasks ×
2 workflows × 5 repetitions**, with twelve active workers by default if subsequently executed. Preparation
does not launch model hosts. The [twelve-task parallel smoke](TASK_LIBRARY_PARALLEL_SMOKE.md)
confirmed twelve overlapping hosts: nine tasks passed and three stopped at the old 8 KiB prompt limit.
The [context-cap removal rerun](CONTEXT_LIMIT_REMOVAL.md) passed all three blocked tasks with the new binary.
The fresh 200-trial batch remains stopped. The earlier
[serial smoke](TASK_LIBRARY_SMOKE.md) records the initial bugs found and corrected.

## Inventory

| Task | Family | Language | Size | Assignment | Private cases |
|---|---|---|---|---|---:|
| [py-log-tally](tasks/python/py-log-tally/TASK.md) | Greenfield | Python | Small | Unicode word frequencies and deterministic ranking | 7 |
| [rust_inventory_rollup](tasks/rust/rust_inventory_rollup/TASK.md) | Greenfield | Rust | Small | Signed inventory aggregation with checked arithmetic | 8 |
| [py-dependency-waves](tasks/python/py-dependency-waves/TASK.md) | Greenfield | Python | Medium | Dependency validation and parallel-ready waves | 7 |
| [rust_build_order](tasks/rust/rust_build_order/TASK.md) | Greenfield | Rust | Medium | Dependency ordering with immediate ready-node selection | 9 |
| [py-document-index](tasks/python/py-document-index/TASK.md) | Greenfield | Python | Large | Recursive text indexing, persisted rebuilds, and search | 4 |
| [py-csv-rollup](tasks/python/py-csv-rollup/TASK.md) | Extension | Python | Small | Add grouped integer totals to a CSV reader | 6 |
| [rust_log_windows](tasks/rust/rust_log_windows/TASK.md) | Extension | Rust | Small | Add half-open time windows to existing log counts | 8 |
| [py-room-calendar](tasks/python/py-room-calendar/TASK.md) | Extension | Python | Medium | Atomic booking rescheduling with overlap checks | 5 |
| [rust_copy_plan](tasks/rust/rust_copy_plan/TASK.md) | Extension | Rust | Medium | Add copy/delete planning to a manifest viewer | 9 |
| [py-ledger-batches](tasks/python/py-ledger-batches/TASK.md) | Extension | Python | Large | Atomic transfer batches with persistent replay receipts | 10 |
| [py-semver-order](tasks/python/py-semver-order/TASK.md) | Bug fix | Python | Small | Repair numeric prerelease ordering and stable ties | 8 |
| [rust_ranges](tasks/rust/rust_ranges/TASK.md) | Bug fix | Rust | Small | Repair nested interval union shrinkage | 7 |
| [py-csv-multiset](tasks/python/py-csv-multiset/TASK.md) | Bug fix | Python | Medium | Reconcile duplicate CSV records across reordered schemas | 7 |
| [rust_ledger_replay](tasks/rust/rust_ledger_replay/TASK.md) | Bug fix | Rust | Medium | Repair nonadjacent replay deduplication and ID conflicts | 10 |
| [py-route-planner](tasks/python/py-route-planner/TASK.md) | Bug fix | Python | Large | Repair directed cheapest-route selection and canonical ties | 7 |
| [py-snapshot-format](tasks/python/py-snapshot-format/TASK.md) | Maintenance | Python | Small | Migrate snapshots to a canonical format while preserving reads | 6 |
| [rust_checked_totals](tasks/rust/rust_checked_totals/TASK.md) | Maintenance | Rust | Small | Replace wrapping invoice arithmetic with overflow errors | 8 |
| [py-durable-queue](tasks/python/py-durable-queue/TASK.md) | Maintenance | Python | Medium | Recover an append log after an interrupted final write | 9 |
| [rust_atomic_export](tasks/rust/rust_atomic_export/TASK.md) | Maintenance | Rust | Medium | Preserve previous files through export failures | 8 |
| [py-batch-checksums](tasks/python/py-batch-checksums/TASK.md) | Maintenance | Python | Large | Isolate individual file failures and preserve ordered reports | 6 |

Python contributes 82 private cases and Rust contributes 67. Size labels describe relative
integration surfaces and required behavior within this collection; they are not calibrated
difficulty ratings or claims of large-repository work. These are small CLI projects with multiple
source files. They cover parsing, data processing, graph algorithms, files, persistence, and
compatibility. The checksum starter contains a worker pool, but parallel execution and worker
count are not independently graded. No HTTP service or production-repository benchmark is present.

Greenfield starters leave the requested behavior unfinished behind a minimal CLI/parser scaffold.
Extensions preserve existing commands while adding a specified operation. Bug fixes provide
symptoms and regression requirements. Maintenance targets specify observable compatibility,
serialization, overflow, or recovery requirements; none rely on subjective code-quality ratings.

## Task and evaluator boundary

Each task directory contains `manifest.json`, `TASK.md`, `project/`, `solution/`, `mutants/`, and
`private/cases.json`. Setup creates a fresh Git baseline from `project/` and copies the fixed task
contract into that repository. The reference patch, mutant labels, private expectations, and local
validation records remain outside the candidate checkout. Setup metadata pins the baseline,
assets, evaluator source, interpreter, and toolchain identity.

Only `src/` and `tests/` are candidate write roots. Task contracts, Cargo/Python metadata, and
grading assets are outside that authority. The campaign policy binds the task contract and scope;
a generated plan or handover cannot enlarge them. The scoped runtime gives implementation access
to the declared write roots plus scratch, and gives verification a read-only candidate with
separate scratch. Scope audits and the independent evaluator check candidate changes. Filesystem
scope does not prove every semantic exclusion, so behavioral assertions remain necessary.

Independent grading uses a stopped candidate, a read-only grading copy, frozen baseline public
tests, and private CLI cases. Candidate-added tests are not independent grading evidence. Each
case gets its own data directory; its steps share that directory so persistence can be checked
across separate processes. Inputs and expected file outputs are UTF-8 bytes, including intentional
CRLF fixtures. Standard output is checked as exact text or contract-equivalent JSON. Error cases
can require individual stderr substrings without prescribing incidental punctuation.

Python uses only the Python 3.12 standard library. Rust uses the standard library, pinned Rust
1.95.0, dependency-free lockfiles, offline/locked Cargo commands, and an isolated build directory.
The Rust projects are detached from the parent Codex workspace. Rust campaigns also require
`--task-just /ABSOLUTE/PATH/just` for the public `just test` recipe. Preparation copies that executable
into the frozen archive's `task-tools/just`, pins it, and grants read access to that helper directory
only; it does not expose the original tool-installation directory. Task commands are argument arrays;
private grading does not interpolate task text into shell commands. The shared grader applies
bounded process time, output, file-size, and filesystem access limits. No private grading feedback
is supplied to a model or used to trigger repairs.

## Offline use

From the repository root, with Python 3.12 in Linux/WSL, list the actual manifests:

```bash
python3.12 lab/experiments/task_library.py list --root lab/tasks
```

Calibrate all 80 variants—20 starters, 20 references, and 40 mutants—using the frozen sandbox and
Rust toolchain paths selected for this release. The output directory must be new and outside the
task assets:

```bash
python3.12 lab/experiments/task_library.py calibrate \
  --root lab/tasks \
  --sandbox /ABSOLUTE/PATH/codex-linux-sandbox \
  --toolchain /ABSOLUTE/PATH/rust-1.95.0 \
  --output /ABSOLUTE/PATH/new-task-calibration
```

The paths above are placeholders, not release artifact locations. Calibration succeeds only when
every reference passes and every starter/mutant fails independent acceptance. It writes
`calibration.json` and per-variant evaluation evidence without model calls. Earlier language-local
self-checks are documented in the pack READMEs; they precede final contract and evaluator fixes
and are superseded for current acceptance by the completed shared sandbox calibration below.

The current generic catalog is [repository-v2.toml](workflows/repository-v2.toml). Its planner makes
relative file paths and phase-local scratch explicit; executor/verifier v1 remain unchanged.

| Workflow | Role instructions and renderer | Maximum repairs |
|---|---|---:|
| `repository-v2` | Generic repository planner/executor/verifier; Markdown plan | 0 |
| `repository-repair-v2` | Inherits the same instructions and renderer | 1 |

Research, planning, implementation, and verification retain separate bounded phases. A repair
uses a separate executor phase after a valid failed verification under the unchanged contract.
These two workflows do not vary handover richness, model selection, or coding procedure.

For the 200-trial offline preparation, use the existing
[run_campaign.py](experiments/run_campaign.py) freezer with the normal pinned binary, provider
home/service receipt, catalog, instruction root, sandbox, and fresh output arguments. Add:

```text
--catalog lab/workflows/repository-v2.toml
--instruction-root lab
--task-root lab/tasks
--task-split study
--task-toolchain /ABSOLUTE/PATH/rust-1.95.0
--task-just /ABSOLUTE/PATH/just
--workflow repository-v2
--workflow repository-repair-v2
--repetitions 5
--jobs 12
--max-amendments 0
--prepare-only
```

`--task-split study` selects the 20 registry tasks and cannot be combined with explicit `--fixture`
arguments. The frozen campaign rotates workflow order across repetitions; it does not implement
the proposed randomized handover study. `--prepare-only` archives and pins the finite trial list;
it does not start trial hosts, generate model plans, or execute candidates. Each admitted trial
later receives its own checkout and policy. Existing legacy fixture selection remains available.

The local Windows launcher is `C:/Users/james/.codex-lab/queue-varied-tasks.ps1`. Its defaults select
all 20 study tasks, both workflows, five repetitions, and twelve jobs. Freeze without launching:

```powershell
& 'C:/Users/james/.codex-lab/queue-varied-tasks.ps1' -PrepareOnly
```

`-Execute <Linuxcampaign.json>` executes an existing frozen campaign. Invoking the launcher without
`-PrepareOnly` or `-Execute` prepares and starts a new campaign. Use the current v2 preparation;
the earlier v1 200-trial preparation predates the sandbox alias fix and should not be launched.

The current bundle is `/home/james/.cache/codex-lab-binaries/task-library-context-v3-20260907`. It reuses
`/home/james/.config/codex-lab/muse-contributor-unattended-v2` unchanged and the existing shared
provider service. Final shared calibration completed successfully:

| Language | Tasks | Variants | Calibration result | Evidence |
|---|---:|---:|---|---|
| Python | 12 | 48 | All expected outcomes matched | `/home/james/.cache/codex-lab-task-calibration/python-final-v1-20260907/calibration.json` |
| Rust | 8 | 32 | All expected outcomes matched | `/home/james/.cache/codex-lab-task-calibration/rust-final-v1-20260907/calibration.json` |

All 20 references passed; all 20 starters and 40 mutants were rejected. Both calibration summaries
record `calibrated=true` and `model_calls=0`. The selected Python harness checks passed 37 unique
tests across scoped runs (32 main harness checks plus five helper checks). The affected runtime
crate passed 104 tests, and the subsequent four focused context-bound regressions also passed.
That initial release enforced an 8,192-byte cap per context section. The subsequent source
change removes harness context-size caps after the parallel smoke exposed ordinary task/plan
prompts exceeding them. Scope permissions and phase budgets remain enforced; model context
capacity and upstream compaction now govern those inputs.
Lint, formatting, format checking, and the final build passed. No tests were rerun after formatting.
The current prepared campaign is `/home/james/.cache/codex-lab-campaigns/varied-library-v3-200-jobs12-20260907/campaign.json`;
all frozen pins validate, and it contains no started trials. The [smoke receipt](task-library-smoke-2026-09-07.json)
records the preceding serial smoke and eight-worker preparation. The [parallel smoke receipt](task-library-parallel-smoke-12-2026-09-07.json)
records the preceding twelve-worker preparation and the original prompt-limit blocker. The
[context-removal receipt](task-library-context-smoke-2026-09-07.json) records the rebuilt binary,
three successful reruns and current twelve-worker preparation. Earlier frozen manifests
are preserved. [Initial offline validation](TASK_LIBRARY_VALIDATION.json)
and the [initial release receipt](task-library-release-2026-09-07.json) remain historical evidence.
The same queue-aware timing calculation is now available through [campaign timing reports](TIMING.md).

## Optional Python dependency runtime

Tasks with Python dependencies can use a separate standalone Python installation.
Install and check the required package versions there before freezing a campaign,
then invoke `run_campaign.py` using that installation's interpreter and pass
`--python-runtime /absolute/standalone/python/prefix`. Virtual environments are
not accepted by this option: task sandboxes already grant read access to the
active interpreter's `sys.base_prefix`, so dependencies must reside within that
same standalone installation. Keep it separate from runtimes used by other runs.

The freezer records the runtime file inventory and hashes its files, including
installed dependencies. Admission and evaluation validate those hashes; changed,
added or removed runtime files invalidate the campaign. The standalone runtime
must contain no bytecode caches or symbolic links: bytecode can execute even
when cache writing is disabled. Copy source files while resolving links and
excluding caches. Use `PYTHONDONTWRITEBYTECODE=1` and `PYTHONNOUSERSITE=1`, and
unset `PYTHONPATH` and `PYTHONHOME`, when preparing and executing an experiment.
This option does not install packages or
enable network access for task candidates. Frozen campaigns without this option
retain their existing interpreter pinning behaviour.

Private repository-derived task packs can be kept outside this repository and
selected with `--task-root`. Source provenance and graders belong outside each
candidate's `project/` directory. Validate the pack's reference solutions and
plausible broken variants using `task_library.py calibrate` before live trials.

## Remaining study work

The broader [workflow study plan](WORKFLOW_STUDY_PLAN.md) remains a roadmap. The compact/evidence
handover matrix, four separate development tasks, eight reserved confirmation tasks, the handover
study's live pilot, richer context retrieval controls, and comparative study report are not implemented by
this task-library increment. All 20 current assignments are in the study split. Existing historical
results remain separate; no previous runs, approvals, candidates, or outcome-based rankings have
been imported into this collection. Repetitions do not turn these synthetic assignments into
independent evidence about all software work.
