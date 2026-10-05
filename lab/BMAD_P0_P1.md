# P0/P1: baseline and truthful workflow results

The baseline is `bmad-baseline.json`. It records the starting commit and SHA-256
of all 24 pre-existing modified/untracked files. Exact original file copies are
kept at the backup path in that manifest, outside this checkout.

The implementation adds `experiments/workflows` as a small result-observation
boundary. `StudySpec` projects the existing frozen campaign manifest and hashes
its full contents; that manifest remains authoritative for the trial matrix,
pins, limits, and execution policy. Preparation writes `study.json`. This is the
legacy-compatible first version, not the future multi-arm experiment designer.

Every new `run_trial` result now has `workflow_result`, separating the terminal
workflow state, confirmed stop evidence, evaluator health, candidate file-map
digest, and acceptance. Existing summary fields remain available. Acceptance
requires a successful evaluator with a matching task, baseline, repository,
run, and workflow-journal hash. Missing/malformed/foreign evidence stays unknown
and retains a failed result record. No exit code alone proves shutdown.

The evaluator still owns the launch lock and validates terminal evidence before
running candidate checks. The adapter reads the evaluator's observation; it does
not create another grading permission or restore execution authority.

New Rust phase artifacts include a compact terminal receipt, produced only
after both the shutdown waiter and graceful marker succeed. Diagnostic retention
is bounded separately and marked when truncated. The Python observer accepts
that receipt while retaining its runtime-journal and scope checks. Old artifacts
continue through the original event-based shutdown validation. Actual shutdown
errors and missing lifecycle evidence still fail closed. Command verification
also remains fail-closed if a required command event was not retained.

Verification before final formatting:

- Python: `test_workflow_contracts test_campaign test_terminal_run
  test_campaign_inputs test_campaign_service test_campaign_python` under WSL
  Python 3.12, with the existing test binary supplied through
  `CODEX_LAB_TEST_BINARY`.
- Rust: focused backend/reports tests and the mocked generated-workflow driver
  test through `just test -p codex-lab-runtime -E ...`.
- Native Windows: campaign import and `run_campaign.py --help`.
- Required `just fmt` uses the existing WSL toolchain and explicit `GIT_DIR` /
  `GIT_WORK_TREE` because this worktree's `.git` file contains a Windows path.
  Formatter-only changes outside this patch are restored byte-for-byte from a
  pre-format snapshot, preserving unrelated work.

No live model campaigns, BMAD installation, SDK session adapter, historical
result rewrites, or full-workspace Rust tests are part of P0/P1. P2 is not started.
