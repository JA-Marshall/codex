# Fresh workflow comparison results

**7/32 candidates passed all independent tests. 31/32 workflows completed.**
All 32 candidates passed the frozen public suite. All 25 candidate failures were
`json_type_idempotency`, in both API and CLI checks: treating JSON true and 1 as the same
original submission specification. The evaluator completed all 73 checks per candidate
(2336 checks total), including 192 two-process claim checks. No previous campaign data is included.

| Planner | Executor | Verifier | Full task pass | Workflow completed | Median active duration |
| --- | --- | --- | --- | --- | --- |
| Concise | Conservative | Focused | 0/4 | 4/4 | 8.2 min |
| Concise | Conservative | Adversarial | 2/4 | 3/4 | 9.6 min |
| Concise | TDD | Focused | 1/4 | 4/4 | 9.1 min |
| Concise | TDD | Adversarial | 0/4 | 4/4 | 9.8 min |
| Architecture | Conservative | Focused | 2/4 | 4/4 | 8.5 min |
| Architecture | Conservative | Adversarial | 0/4 | 4/4 | 9.4 min |
| Architecture | TDD | Focused | 1/4 | 4/4 | 9.5 min |
| Architecture | TDD | Adversarial | 1/4 | 4/4 | 9.6 min |

Concise/conservative/adversarial and architecture/conservative/focused tied at 2/4.
Four trials per combination on one task are insufficient to establish a general winner.
See [summary](summary.json), [per-condition results](conditions.json) and
[paired executor/verifier comparisons](paired-comparisons.json).

## What this run establishes

- All 32 approved targets ran once, with a measured peak of 16 active jobs.
- Execution took 23.9 minutes, excluding preparation and independent evaluation.
- Shared proxy: 1535 execution requests, all HTTP 200; peak 92 requests in any observed 60-second window, zero 429s.
- Receipt service: 139 successful lookups in completed phase artifacts, including 11 omitted-preview receipts, zero incomplete/ambiguous faults.
- Repair budget was two rounds per trial; **zero harness repair rounds occurred**. The verifiers did not submit failed verification evidence that triggered a repair. Hidden failures were not fed back into agents.
- Six original planner samples were approved unchanged; two received the explicitly approved field-count corrections. Plans were shared only within each fresh block/planner group.

## Failure and measurement limits

`queue-r3-aab-execution-reviewed` failed with phase shutdown evidence limit exceeded.
The workflow remains failed, with incomplete shutdown evidence. Its saved candidate was
scored separately using the same frozen evaluator function; it also failed the idempotency
check. Its evaluation is labelled `candidate_only`, and no clean shutdown or workflow
success is inferred. The harness was not changed or restarted to rescue it.

Confirmed terminal-run usage is 40,069,488 tokens:
38,663,725 input, 1,405,763 output,
including 35,998,510 cached input tokens.
This excludes the failed run with incomplete phase evidence and is a **lower bound**,
not total billed usage. Preparation added 253615 tokens. Model-call metadata covers
recorded stopped phases; the provider trace separately records all dispatched requests.
No immutable Muse serving revision or enforced cumulative token/spend cap is claimed.

The dominant gap is verification sensitivity: 24 workflows completed despite failing
independent correctness checks. One additional incorrect candidate belonged to the failed
workflow. Longer runs or the presence of a repair loop alone did not expose this defect.
A future experiment could test stronger contract-derived verification instructions; these
results and candidates must stay frozen, and hidden answers must not be silently added to
an otherwise identical condition. The evidence-size failure is a separate harness issue.

## Evidence

[Human approval](../execution-approval.json), [review packet](../REVIEW.md),
[batch outcomes](batch-result.json), [provider trace](provider-events.jsonl),
[receipt health](receipt-health.json), [model-call metadata](model-calls.jsonl),
[raw trace inventory](trace-inventory.json), and [export hashes](export.json).
Each condition directory contains the final diff, independent evaluation summary,
workflow/event journals and artifact inventory. Full evaluations and raw traces remain at
`/home/james/.cache/codex-lab-queue-matrix/20260907T190853Z-fresh-v1`. Evaluator version and code/input fingerprints are retained per evaluation.
No candidate, test result, approval or outcome was imported from a pre-reset campaign.
