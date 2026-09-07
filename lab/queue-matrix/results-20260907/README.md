# Queue workflow matrix results

All **28 approved executions finished**, with peak concurrency eight. The model
batch took **33 minutes 15 seconds** from first dispatch to last exit. There were
no retries, amendments or replacement planner samples.

**22/28 workflows completed. 11/28 candidates passed the contract-audited checks.**
The original frozen evaluator passed 9/28; its overly strict Unicode serialization
check caused two false task failures. Both scores and the explicit audit are retained.
All 28 candidates passed the three public tests and all 168 two-process claim checks.
The remaining 17 candidates share a narrow bug: treating payload JSON `true` and
`1` as equivalent when checking idempotent resubmission.

## Combinations

Letters select planner/executor/verifier respectively:
planner A = concise, B = architecture/risk-first;
executor A = conservative/minimal-diff, B = TDD;
verifier A = focused tests, B = adversarial tests/review.
These labels identify pinned instructions; full procedural compliance was not
independently scored. Most plans group regression tests into their final step,
which may interact with test-first executor instructions.

| Combination | Trials | Frozen task pass | Audited task pass | Workflow complete | Median active time | Mean execution tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AAA | 3 | 0 | 1 | 2 | 7.4 min | 1.163M |
| AAB | 3 | 1 | 1 | 3 | 8.0 min | 1.395M |
| ABA | 3 | 1 | 1 | 3 | 6.4 min | 1.198M |
| ABB | 3 | 1 | 2 | 2 | 9.2 min | 1.763M |
| BAA | 4 | 3 | 3 | 4 | 5.7 min | 0.558M |
| BAB | 4 | 2 | 2 | 2 | 10.1 min | 1.708M |
| BBA | 4 | 0 | 0 | 4 | 7.0 min | 1.186M |
| BBB | 4 | 1 | 1 | 2 | 9.5 min | 1.609M |

**BAA had the strongest observed result:** architecture-first planning,
conservative execution, focused verification passed three of four candidates,
completed all four workflows and used the fewest mean execution tokens. This is
an exploratory result on one task, not evidence of a universal winner.

Across the seven shared-plan blocks, conservative execution passed 7/14 candidates
and TDD passed 4/14 after the audit. In 14 comparisons holding the plan and verifier
selector fixed, conservative alone passed six pairs, TDD alone passed three,
and five tied. The two comparisons per plan are not independent planner samples.

Verifier A completed 13/14 workflows; verifier B completed 9/14. Five failures
used output chunk IDs instead of command call IDs; one used an unknown acceptance
criterion. **Three correct candidates failed this report protocol**, while
**14 incorrect candidates completed the workflow**. Improving report validity
and improving bug detection are separate problems.

Do not interpret differences in candidate correctness between verifier variants
as a causal verifier effect. Their executors produced independent candidates,
and this matrix is not a fixed-candidate verifier replay. The verifier replay
mechanism is available for a separate controlled follow-up; no such runs were
authorized or started here.

## Frozen score and serialization audit

The contract requires a sorted-key JSON value and one final newline. The frozen
worker additionally required the exact bytes of Python's default `json.dumps`,
including ASCII escapes. Literal UTF-8 such as `é` is valid under the contract.

The original evaluator and its 73 checks were run unchanged for all 28 candidates.
The separately identified [audit](cli-format-audit/audit.json) then rechecked only
`durable_views/cli`, uniformly across all candidates, using a validator that accepts
equivalent JSON escaping/spacing while checking sorted unique object keys, valid
UTF-8/finite JSON, one value and one final newline. Two focused tests validate
accepted styles and reject malformed, unsorted, duplicate and nonfinite output.

The audit changed five check outcomes and two overall task scores. It made no
model calls or candidate changes. Original scores, full evaluation hashes and
raw observations remain intact. The audit worker, parser and driver are exported
as exact text artifacts alongside their hashes. This is explicitly a post-hoc
contract audit, not a claim that the corrected evaluator was preregistered.

## Usage and controls

- Execution: 35,458,556 input + 1,337,193 output = **36,795,749 tokens**.
  Cached input is 33,093,541 and is already included in input.
- Preparation, including the failed planner: **251,977 tokens**.
- Campaign total: **37,047,726 tokens**, about 53 times the earlier 698,679-token
  pilot and 5.9% above the approximate 35M allocation. The allocation was not a
  hard token or spend cap; no dollar cost is inferred from these counts.
- Execution model calls: **1,459**. Preparation model calls: 64.
- Peak concurrency: eight hosts, eight phases and eight model requests.
  Eight-request overlap totals 606.905 seconds; this includes network/provider
  queueing and does not prove simultaneous server-side computation.
- All 56 execution phases have shutdown evidence; all admitted tools have terminal
  results and were preceded by the exact approved target. All 28 hosts exited.
- Model/provider, task commit, Markdown, limits, role bytes and evaluator cases
  remained pinned. No model serving revision beyond the requested model ID was
  reported.

The user explicitly accepted 11 proposed text corrections across five of seven
valid plans. Only two of eight original planner samples reached approval without
correction; one failed schema validation and blocked its three dependents. Shared
plan costs are counted once. Planner comparisons therefore include human-reviewed
corrections and must not be presented as raw planner performance alone.

## Evidence and validation

[summary.json](summary.json) contains aggregate and paired results;
[conditions.json](conditions.json) contains every executed condition, its approval,
phase usage, verifier report, Git diff metadata and check failures. The original
[preparation conditions](../conditions.json) retain the failed planner and three
blocked conditions. Every run directory here contains compact evaluation results,
the exact candidate diff, terminal observations and event journals. Full evaluation
JSON and raw model traces remain local with published hashes.

The frozen campaign root is
`/home/james/.cache/codex-lab-queue-matrix/20260907T163300Z`.
No benchmark candidate was manually repaired or merged into the Codex product.
The old ten verifier-only preparations remain untouched and unlaunched.

Independent evaluation ran after all model hosts exited, using the existing Codex
Linux sandbox. All 28 evaluations completed. The separate audit confirmed candidate
file/diff identity before and after each observation. The new validator's two
focused tests passed, followed by formatting; no full workspace test suite ran.

Task success here means success on this finite corpus. The binary pass rate is
dominated by one subtle JSON-type edge case, so more tasks are needed before
choosing a general-purpose workflow. Plan deviations remain unscored.
