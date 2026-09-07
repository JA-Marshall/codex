# Varied-task execution results — 2026-09-07

All four approved candidates passed the independent evaluator. Both configuration workflows completed; both dependency workflows failed because the verifier submitted multiple observations for one verification ID. These runs establish useful correctness and harness diagnostics, but do not establish a preferred plan renderer.

| Task | Renderer | Workflow | API cases | CLI cases | Fixed public tests | Independent task success |
| --- | --- | --- | --- | --- | --- | --- |
| Dependency ordering | JSON | failed | 14/14 | 14/14 | 3/3 | true |
| Dependency ordering | Markdown | failed | 14/14 | 14/14 | 3/3 | true |
| Configuration merging | Markdown | completed | 14/14 | 14/14 | 3/3 | true |
| Configuration merging | JSON | completed | 14/14 | 14/14 | 3/3 | true |

Execution order was dependency JSON, dependency Markdown, configuration Markdown, configuration JSON. Each condition received exactly one attempt after the user approved its exact target. No amendment, human plan edit, retry or manual candidate repair occurred. All eight phase threads shut down; no live run or human decision remains pending.

## What the experiment showed

The dependency JSON verifier reported `v-cli` five times; Markdown reported it twice. Both reported `v-unittest` once. The unchanged host requires exactly one check record per planned verification ID and rejected both with `every planned verification requires one observation`. The external evaluator then validated shutdown and checkout identity, acquired the launch lock and tested each candidate independently. Passing candidates did not erase the workflow failures or fill missing original host metrics.

The configuration verifiers each reported V1 and V2 once, satisfying the existing evidence contract. Both candidates passed the same fixed evaluation corpus. The configuration comparison is `controlled_recorded_pair`; the dependency comparison remains `descriptive_only` because its workflows failed and original final host metrics are absent. Both comparisons record only `plan.renderer` as a differing experimental control.

This is a concrete demonstration that candidate correctness and workflow completion need separate measures. The repeated verifier-report failure now occurs on dependency ordering as well as the historical CSV task. It is a useful next investigation, independently of plan representation.

## Execution costs

| Metric | Dependency JSON | Dependency Markdown | Configuration Markdown | Configuration JSON |
| --- | ---: | ---: | ---: | ---: |
| Phase turns / observed inference calls | 2 / 44 | 2 / 41 | 2 / 32 | 2 / 36 |
| Tool admissions | 49 | 46 | 33 | 41 |
| Input tokens | 428,670 | 376,166 | 268,130 | 326,010 |
| Cached input tokens (included above) | 397,578 | 346,039 | 242,878 | 290,321 |
| Output tokens | 13,790 | 12,335 | 9,490 | 11,018 |
| Time through terminal workflow event | 174.358 s | 225.343 s | 126.072 s | 148.877 s |
| Final host wall time | unavailable | unavailable | 138.060 s | 160.847 s |
| Files changed / diff bytes | 3 / 7,004 | 3 / 6,083 | 3 / 7,001 | 3 / 5,821 |

These are execution-only observations. Preparation of the shared dependency plan used 19,300 input / 3,271 output tokens; the configuration plan used 20,685 input / 4,343 output tokens. Each took two research/planning phases, and its JSON preparation imported the same canonical bytes with zero model calls. Execution planner phases are zero for every condition. The excluded fresh CSV preparation cost is retained in the review receipt, not charged to these four executions. Wall times retain approval-wait and host overhead; terminal event time is distinct from final host time and external evaluation time.

No cost ranking is reliable from one observation per condition. There is no hard cumulative token/spend cap, immutable remote serving revision or independent plan-deviation score. Passing the evaluator means passing this finite diagnostic corpus, not all possible inputs.

## Historical CSV anchor

The previously executed CSV candidates were reevaluated before this four-run approval. Markdown remains workflow failed, with API 20/21 and CLI 20/21; JSON remains completed, with API 21/21 and CLI 20/21. Both passed 3/3 fixed public tests and failed independent task success on quoted-newline behavior. Those are historical candidates, not new samples in this session. The newly prepared CSV targets were not executed. See the preserved [review and historical evaluations](REVIEW.md).

## Evidence and reproducibility

- [Human execution approval](execution-approval.json), [exact reviewed targets](review-targets.json), and [frozen suite manifest](suite.json).
- [Result receipt and source artifact hashes](results-2026-09-07.json).
- [Dependency comparison](dependency-order-v1-comparison.json) and [configuration comparison](config-merge-v1-comparison.json), copied without modification from the fixed comparison command.
- Dependency [JSON evaluation](dependency-order-v1-json-execution-evaluation.json) / [observation](dependency-order-v1-json-execution-observation.json), and [Markdown evaluation](dependency-order-v1-md-execution-evaluation.json) / [observation](dependency-order-v1-md-execution-observation.json).
- Configuration [Markdown evaluation](config-merge-v1-md-execution-evaluation.json) / [observation](config-merge-v1-md-execution-observation.json), and [JSON evaluation](config-merge-v1-json-execution-evaluation.json) / [observation](config-merge-v1-json-execution-observation.json).

Frozen local root: `/home/james/.cache/codex-lab-varied-pilot/20260907T134224Z`. Requested model: `muse-spark-1.3-contributor`. Source commit: `6d0530fb92515be69c01238d9c2c4c4775c9715f`. Binary, provider configuration/catalog, interpreter, role instructions, task inputs and evaluator pins were rechecked. Within each pair, canonical plan and baseline commit match. The recorded approval target precedes every admitted tool; parent preparations remain unchanged and unapproved.

Run journals, phase evidence, final candidate diffs and model traces remain in the local root. The published observations are separate read-only measurements, not restored execution authority. Raw model traces and credentials are not published. Original review snapshots and failed-run journals remain unchanged. Hashes detect subsequent drift; they do not attest remote model weights or a malicious host.

## Next bounded investigation

Propose a separately versioned verifier instruction that explicitly requires one report entry per verification ID and explains how to run one aggregate assertion command for multi-scenario criteria. Keep the strict completed-command evidence join and approval gate unchanged. Check the contract with focused tests before another separately approved live experiment. Hold renderer, model, canonical task plan and executor constant while varying only that verifier instruction.

This follow-up is a proposal, not an implemented change or authorization for more runs. No Rust/core/provider/TUI or harness source changed in this results iteration. Validation comprised the four frozen sandbox evaluations, artifact/control/approval checks and documentation checks; the prior eight focused Python tests remain the implementation validation. No full workspace test suite was run.
