# Rust repository tasks

Eight independent synthetic CLI projects, all assigned to the `study` split. Each family has one small and one medium task, with a distinct `project_id` equal to its task ID. These are bounded coding assignments, not evidence of performance on production repositories.

| ID | Family | Size | Objective | Private cases |
| --- | --- | --- | --- | ---: |
| `rust_inventory_rollup` | greenfield | small | Build signed inventory aggregation | 8 |
| `rust_build_order` | greenfield | medium | Build deterministic dependency ordering | 9 |
| `rust_log_windows` | extension | small | Extend log counts with half-open time windows | 8 |
| `rust_copy_plan` | extension | medium | Extend manifest listing with copy/delete planning | 9 |
| `rust_ranges` | bug_fix | small | Repair nested interval union shrinkage | 7 |
| `rust_ledger_replay` | bug_fix | medium | Repair nonadjacent event deduplication and conflicts | 10 |
| `rust_checked_totals` | maintenance | small | Replace wrapping arithmetic with complete overflow errors | 8 |
| `rust_atomic_export` | maintenance | medium | Preserve destination files through failed exports | 8 |

Every task contains a fixed `TASK.md`, a detached `project/` Cargo repository, a reference `solution/` overlay, two `mutants/` overlays, and host-side `private/cases.json`. The starter has multiple source files and existing public tests. Greenfield starters contain an explicitly unfinished engine with implemented parsing; the other starters implement the prior behavior or demonstrate the reported defect. All 16 mutants retain the public examples and fail private cases.

Projects use only the standard library, Rust 1.95.0, committed dependency-free Cargo lockfiles, and their own `[workspace]` declaration. Writable candidate paths are limited to `src/` and `tests/`. No Codex runtime crate, existing experiment run, live model, network service, or downloaded package is involved.

For fixture-local public checks, first copy `project/` into a disposable directory and apply the desired overlay. Load the pinned toolchain environment, set `CARGO_TARGET_DIR` to a separate scratch directory, then run `just --justfile <copy>/justfile --working-directory <copy> test`. The manifest's `public_command` is the evaluator protocol; it executes the same offline, locked Cargo test operation. Do not place build output in the task assets or use the parent Codex target directory.

`validation-local.json` records direct local checks of 32 variants: 8 starters, 8 reference solutions, and 16 mutants. All 32 built and passed their public tests. Each reference passed all of its private cases (67 total); every starter and mutant failed at least one private case. This local evidence does not establish sandbox isolation; run the shared `lab/experiments/task_library.py calibrate` evaluator separately for that check. The atomic-export cases establish normal success, validation failure preservation, temporary-file collision preservation, and rename-failure cleanup. They do not establish crash or power-loss durability, which is excluded from the task contract.

Final shared Linux sandbox calibration passed all 32 expected variant outcomes after the contract and grader corrections. The receipt is `/home/james/.cache/codex-lab-task-calibration/rust-final-v1-20260907/calibration.json`; see [the library validation](../../TASK_LIBRARY_VALIDATION.json) for the full validation scope.

Private cases, reference solutions, mutant labels, and validation results are host-side evaluator assets and must not be included in a model's candidate repository or task prompt.
