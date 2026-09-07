# Harness context caps removed

The new binary removed the harness's phase/task/instruction context-size caps. Fresh reruns of the three tasks blocked by the old limit finished 3/3 successful, in 485.481 seconds for the complete campaign. The 200-trial campaign remains unstarted with twelve workers configured.

| Task | Independent result | Largest phase prompt | Host time | Queue wait |
| --- | --- | ---: | ---: | ---: |
| rust_copy_plan | Pass | 8,673 bytes | 437.974s | 2.652s |
| rust_checked_totals | Pass | 7,899 bytes | 481.079s | 2.869s |
| rust_atomic_export | Pass | 8,931 bytes | 303.597s | 0.897s |

The former 8 KiB phase fragment, 16 KiB combined, 8 KiB task-loading and 12 KiB instruction-file caps are gone. Effective runtime settings record null harness context limits. The existing configured model window is 1,048,576 tokens; upstream compaction remains in charge. Separate phases, scope permissions, repair budgets and the thirty-minute phase timeout remain. The shared provider configuration and 100-request/minute limiter were unchanged.

Validation passed 143 tests in the two affected Rust components and four Python matrix checks. One existing prepared-plan comparison timed out under concurrent testing and passed its automatic retry. Scoped lint and changed-file formatting checks passed. A regression carries a large task, lossless plan and long frozen roles through actual sandboxed coding and verification; others cover large model/permission instructions and prepared-run task preservation. The full workspace suite was not run.

These are fresh candidates and newly generated plans, not a paired speed comparison. Three reruns validate the cap removal; the earlier smoke established twelve overlapping hosts. Native context limits, plan structure, tool-output and artifact resource bounds still apply.

Current bundle: `/home/james/.cache/codex-lab-binaries/task-library-context-v3-20260907`. Prepared full campaign: `/home/james/.cache/codex-lab-campaigns/varied-library-v3-200-jobs12-20260907/campaign.json`. All prior full campaign manifests retain their original hashes and remain unstarted. See [the full receipt](task-library-context-smoke-2026-09-07.json), [the earlier parallel smoke](TASK_LIBRARY_PARALLEL_SMOKE.md), and [context handling](RUNNING.md).
