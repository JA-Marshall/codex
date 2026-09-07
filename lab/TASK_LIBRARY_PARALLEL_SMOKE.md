# Twelve-task parallel smoke

The launcher now defaults to twelve workers. This smoke finished 9/12 successful trials, with 12 model hosts overlapping and 371 seconds elapsed for the complete campaign, including setup and independent grading. The 200-trial campaign remains unstarted.

The shared 100-request/minute limiter was unchanged. The campaign made 328 model requests, with a peak of 89 shared dispatches in a rolling minute and up to 5.767 seconds waiting for an individual request. All 328 responses returned HTTP 200. The thirty-minute phase timeout still includes provider waiting.

| Task | Task checks | Host exit | Grader exit | Host seconds | Queue seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| py-log-tally | Pass | 0 | 0 | 367.196 | 25.197 |
| py-dependency-waves | Pass | 0 | 0 | 291.097 | 31.479 |
| rust_inventory_rollup | Pass | 0 | 0 | 348.622 | 25.325 |
| py-csv-rollup | Pass | 0 | 0 | 243.141 | 29.688 |
| rust_log_windows | Pass | 0 | 0 | 315.400 | 29.819 |
| rust_copy_plan | Fail | 1 | 0 | 139.165 | 13.104 |
| py-semver-order | Pass | 0 | 0 | 252.993 | 31.045 |
| py-csv-multiset | Pass | 0 | 0 | 324.159 | 24.446 |
| rust_ranges | Pass | 0 | 0 | 270.426 | 28.179 |
| py-snapshot-format | Pass | 0 | 0 | 317.797 | 31.036 |
| rust_checked_totals | Fail | 1 | 0 | 116.550 | 6.411 |
| rust_atomic_export | Fail | 1 | 0 | 121.494 | 11.496 |

Each task ran once using `repository-repair-v2`, allowing at most one repair. The subset has three tasks per family, six Python and six Rust, eight small and four medium assignments. This is a throughput smoke, not an isolated speed comparison. Larger tasks, sustained 200-trial load and a thirty-minute queue stall remain untested.

Three tasks stopped before implementation because their complete task-and-plan prompt exceeded the 8,192-byte limit: rust_copy_plan used 8,256 bytes, rust_checked_totals 8,510, and rust_atomic_export 8,232. They obeyed the planner step/check limits. This deterministic prompt-size check is independent of worker concurrency and provider timing. The prompt limit was not changed in this run. Address it before launching the 200-trial campaign; a bounded option is a separate 12 KiB prompt cap while retaining the 8 KiB instruction limit and 16 KiB combined envelope, with regression checks for the three retained plans.

The new 200-trial preparation is `/home/james/.cache/codex-lab-campaigns/varied-library-v2-200-jobs12-20260907/campaign.json`, with twelve workers. Older preparations, candidates and results were preserved. See [the full receipt](task-library-parallel-smoke-12-2026-09-07.json), [the earlier serial smoke](TASK_LIBRARY_SMOKE.md), and [timing semantics](TIMING.md).
