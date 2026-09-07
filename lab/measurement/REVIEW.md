# Varied-task review and measured failure

The measurement work is implemented and tested. Six new preparations have exited with unapproved canonical plans; no new task implementation has run. This packet contains review data, not saved authority. The existing runtime will still display and require a decision for each exact execution target.

## What the failed-run measurement established

| Historical condition | Workflow state | API cases | CLI cases | Fixed public tests | Independent task success |
| --- | --- | --- | --- | --- | --- |
| Markdown | failed | 20/21 | 20/21 | 3/3 | false |
| JSON | completed | 21/21 | 20/21 | 3/3 | false |

Both candidates fail the quoted-newline case. Markdown rejects a valid multiline quoted category; JSON preserves it through the API but normalizes embedded CRLF through its CLI. The Markdown report failure no longer hides its candidate correctness. Its workflow stays failed.

These are deliberately **new evaluations** of unchanged old candidates with the frozen current evaluator. Original pilot artifact hashes were checked against the previously published receipt and remain identical. The reports retain original and current evaluator fingerprints. Evidence: [Markdown evaluation](old-pilot-md-evaluation.json), [Markdown observation](old-pilot-md-observation.json), [JSON evaluation](old-pilot-json-evaluation.json), [JSON observation](old-pilot-json-observation.json). Candidate diffs remain in the local suite's `old-pilot-reevaluation/` directory.

## Recommended next executions: four new-task targets

1. **Dependency ordering:** implement validated lexicographic Kahn ordering, reject unknown dependencies/cycles, preserve inputs, and test API/CLI behavior. Review [canonical JSON](dependency-order-v1.plan.json) or [Markdown](dependency-order-v1.PLAN.md). Run JSON first, then Markdown.
2. **Configuration merging:** implement recursive object precedence, replacement semantics and input preservation; test invalid roots and CLI behavior. Review [canonical JSON](config-merge-v1.plan.json) or [Markdown](config-merge-v1.PLAN.md). Run Markdown first, then JSON.

Both plans are sufficiently concrete for implementation review. Their CLI verification criteria cover multiple scenarios; the unchanged verifier contract requires **one check record per verification ID**, so an aggregate assertion command may be needed. No schema relaxation or procedural instruction change was introduced for this experiment. The configuration plan's phrase "deep-ish" is imprecise, but its explicit no-input-mutation acceptance criterion governs the result.

Exact targets are in [review-targets.json](review-targets.json). The four recommended run IDs are:

- `dependency-order-v1-json-execution`
- `dependency-order-v1-md-execution`
- `config-merge-v1-md-execution`
- `config-merge-v1-json-execution`

An approval of these four targets does not approve any future amendment. Their canonical hashes are `0eadb6d14529a2989108b40ffbbb8e44bbca0b0be88e776b8424730c74449a53` (dependency ordering) and `0435406d6f40cc74eb0a175cf5415d58c68c0f13b573842d0346f85bbba471bd` (configuration merging), both plan `task-plan`, revision 1. The JSON target file includes each distinct run-spec hash. Verify those fresh displayed targets before transmitting an authorized decision.

## Retain CSV as a historical anchor

The newly generated [CSV plan](csv-summary-v1.PLAN.md) repeats the known newline-normalizing `read_text` approach. Its strict-reader description also does not explicitly address bare quotes or full-string count validation. Recommend **not executing this new CSV plan as written**. Both new CSV targets are retained but are excluded from the four-target recommendation.

Use the already executed, newly evaluated CSV pair as a labelled historical diagnostic anchor. This changes the suggested next execution set from six fresh attempts to four; it avoids two redundant attempts while retaining three task types for descriptive analysis. It is an explicit follow-up recommendation after plan review, not a silently changed preregistration. The original [suite manifest](suite.json), all six preparations and earlier plans remain unchanged. Historical CSV results are not new independent samples. If a fresh CSV pair is later wanted, prepare and review a corrected canonical revision first.

## Controls and readiness

Frozen suite root: `/home/james/.cache/codex-lab-varied-pilot/20260907T134224Z`. Source commit: `6d0530fb92515be69c01238d9c2c4c4775c9715f`. Requested model: `muse-spark-1.3-contributor`. Existing host binary, provider configuration/catalog and v1 planner/executor/verifier instructions are unchanged from the prior pilot; no immutable remote serving revision is known.

Within each new pair, canonical bytes and all RunSpec controls match after excluding only renderer and workflow-name/inheritance metadata. Each preparation's sealed artifact digests passed validation; all model phase threads contain shutdown receipts, all six repositories retain their clean baseline, and no execution directory exists. JSON preparations imported the paired plan without model calls. Total new preparation usage: 60,907 input and 12,536 output tokens across six phase threads; individual costs are recorded in the target receipt.

Existing runtime/context caps and attempt limits are in the manifest. There is no new hard cumulative token/spend cap. No automatic retries, approvals or amendment decisions are supplied by the preparation coordinator. Existing comparison labels remain conservative for failed runs; report workflow state, evaluated correctness and missing measurements separately, without a statistical winner claim.

Eight focused Python tests passed, including real-sandbox calibration of all three tasks and failure/lock/drift protections. Final formatting passed and preserved all tested Python ASTs. See [validation receipt](../measurement-validation-2026-09-07.json) and [progress ledger](../PROGRESS.md).
