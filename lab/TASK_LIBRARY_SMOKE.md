# Task-library live smoke and timing

The corrected pipeline passed both live tasks: Python greenfield word counting and a Rust interval-merging bug fix. Both ran serially through the unchanged shared Muse limiter. The 200-trial batch has not started.

The timer change from `a359dd91e5` is now included: reports retain actual elapsed time, provider queue-wait union, and the observed remainder. The existing 30-minute phase safety timeout still includes queue waiting. It was not paused or extended.

| Corrected task | Result | Host elapsed | Limiter wait | Private checks |
| --- | --- | ---: | ---: | ---: |
| py-log-tally | Pass | 313.28s | 1ms | 7 |
| rust_ranges | Pass | 269.92s | 1ms | 7 |

Both candidates passed public and private checks, stayed within scope, and stopped all phases. This small serial run had negligible queue waiting; it does not establish behavior under heavy contention or a success rate across all 20 tasks. Overlapping queue waits and competing traffic are covered by focused timing tests.

The first two attempts exposed a sandbox-dispatch alias bug in the freezer and an underspecified planner path rule. Python stopped at plan validation; Rust completed but the grader invocation failed. Separate posthoc grading confirmed the original Rust candidate passed and the unfinished Python candidate failed. Those original attempts and result files remain intact; the corrected run uses fresh candidates and the versioned v2 planner.

The current launcher uses the corrected timing-v2 bundle and repository-v2 workflows. The fresh 200-trial preparation is `/home/james/.cache/codex-lab-campaigns/varied-library-v2-200-20260907/campaign.json`. It contains 20 tasks × two workflows × five repetitions at eight jobs, and remains unstarted. The earlier v1 200-trial preparation is historical and should not be launched.

See [the machine-readable receipt](task-library-smoke-2026-09-07.json) for exact versions, hashes, original failures and timing evidence, and [TIMING.md](TIMING.md) for measurement semantics.
