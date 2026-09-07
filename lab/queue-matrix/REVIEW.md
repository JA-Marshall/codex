# Queue instruction matrix: human review

**No implementation is approved or running.** Recommended next action: approve
the 28 exact targets in [review-targets-recommended.json](review-targets-recommended.json),
including the explicitly proposed corrections below, for one execution attempt
each with concurrency eight. Approval would accept those corrections; it would
not authorize automatic amendments, retries, or replacement of the failed sample.

## What was prepared

The [task contract](../fixtures/durable-queue-v1/project/CONTRACT.md) specifies a
durable SQLite queue with dependencies, atomic claims, leases, retries and a JSON
CLI. The matrix varies concise/architecture-first planning, conservative/TDD
execution and focused/adversarial verification. Model, provider settings,
Markdown, task bytes, repository commit and harness limits remain constant.

Eight research/planning samples ran concurrently: two planners across four
replicate blocks. Seven returned schema-valid plans; each was imported into four
executor/verifier conditions. One sample failed with duplicate verification ID
`V3`; its three dependents were blocked, without retry. This leaves **28 pending
execution conditions**, not 32 successful preparations. Every original result is
preserved in [conditions.json](conditions.json).

Preparation used **251,977 reported tokens**: 206,498 input (including 121,633
cached input) and 45,479 output. This includes the failed planner. There were
16 phase threads, 64 model calls and 163 read-only repository tool calls. All
16 phases emitted shutdown completion; all 32 task checkouts remain clean.
Observed peak concurrency was eight phases and eight actual model requests;
eight requests overlapped for 22.476 seconds in aggregate. See
[summary.json](summary.json) and [model-calls.json](model-calls.json).

The roughly 35M-token allocation includes later implementation and verification.
It is not a hard spend/token cap or a requirement to consume the allocation.

## Proposed corrections, still unapproved

Schema-valid does not mean semantically correct. Review found 11 text corrections
across five plans. [changes.json](proposed-edits/changes.json) records every exact
before/after value and original/proposed plan digest. Originals remain untouched.
The corrected plans were imported into 20 new preparations with **zero model
calls**. Their RunSpecs are byte-identical to the corresponding originals;
only the plan and run identities change. The other eight recommended conditions
use their original preparations. All four conditions sharing a plan receive the
same proposed correction.

| Planner sample | Original | Recommended plan | Correction |
| --- | --- | --- | --- |
| Concise, block 1 | [plan](plans/queue-r1-aaa.md) | original | None |
| Architecture, block 1 | [plan](plans/queue-r1-baa.md) | [proposed](proposed-edits/queue-r1-baa.md) | Ten view fields, not twelve; relational validation inside the write transaction; one claimant gets the sole lease and the other gets null |
| Concise, block 2 | [plan](plans/queue-r2-aaa.md) | original | None |
| Architecture, block 2 | [plan](plans/queue-r2-baa.md) | [proposed](proposed-edits/queue-r2-baa.md) | Retry count is bounded; retry delay is any nonnegative integer |
| Concise, block 3 | [invalid output](failed/queue-r3-aaa-plan.json) | none | Duplicate V3; failed sample and three blocked dependents retained |
| Architecture, block 3 | [plan](plans/queue-r3-baa.md) | [proposed](proposed-edits/queue-r3-baa.md) | Ten view fields, not twelve |
| Concise, block 4 | [plan](plans/queue-r4-aaa.md) | [proposed](proposed-edits/queue-r4-aaa.md) | Bound attempts, not retry delay; an unavailable database is an error, a missing database file may be created |
| Architecture, block 4 | [plan](plans/queue-r4-baa.md) | [proposed](proposed-edits/queue-r4-baa.md) | Submission results preserve input order; only list sorts by ID |

These are assistant proposals, not recorded human edits or approvals yet. If
accepted, analysis must include the intervention and distinguish original-plan
quality from performance after correction. Do not attribute corrected execution
outcomes solely to raw planner quality. Other rough wording in original discoveries
is retained as model output rather than silently rewritten.

Commands such as `--db PATH --request FILE` in plans denote temporary fixtures
the executor/verifier must create. Verification instructions require one real
aggregate receipt per verification ID; placeholder commands or zero-test success
are not evidence that acceptance criteria passed. Each independent evaluation
uses the frozen contract, regardless of a model's own tests or completion claim.

## Exact inputs and pending authority

- Recommended batch: [batch-input-recommended.json](batch-input-recommended.json),
  SHA-256 `09c43895ae2e3d99f9be0263400c5de426083bc8a733df6675ac9a12e3b7b1e3`.
- Live recommended batch is under
  `/home/james/.cache/codex-lab-queue-matrix/20260907T163300Z/proposed-edits/`.
- Source commit: `f0459593f8e0f864f8800dafdc4f043598021bb3`.
- Identical task baseline: `689b3bd49dd3ef4f746481e909edfad041ab16b0`.
- Versioned host binary SHA-256:
  `dc5b99261abbfb0831836c1586125a3db0a2a4b6f54d51ac26243dedfcfd01d1`.
- Model: `muse-spark-1.3-contributor`, existing `muse-lab` Responses provider.
  An immutable serving revision was not reported. Configuration pins do not
  establish an immutable backend revision.
- Configured context: 1,048,576; compaction threshold: 900,000. Phase token
  events reported 996,147 usable context consistently. Both are recorded.

[matrix.json](matrix.json) freezes the source, model/catalog/interpreter/binary
pins, role selectors, order and limits. [effective-settings.json](effective-settings.json)
and [environment.json](environment.json) preserve the effective settings and
runtime metadata. The API key is absent from the export.

[preflight-recommended.json](preflight-recommended.json) confirms 28 distinct
checkouts, fresh execution destinations and jobs=8. Preflight is read-only and
does not grant approval. At launch, the coordinator must match each live review
request against its complete recommended target before sending an approval.
Superseded original preparations remain unapproved and must not also be launched.

All original artifacts/traces are hashed in [artifact-inventory.json](artifact-inventory.json);
new proposed preparations are hashed in [proposed-edits/inventory.json](proposed-edits/inventory.json).
Raw local traces and failed output remain available. The failure event's final
`shutdown_confirmed` field is false after validation failure; both actual phase
records contain `shutdown_complete`, phase intervals close, and every admitted
tool has a terminal result. No active phase/dispatch is left behind.

## Validation and next execution step

The foundation passed 23 scoped lab Python tests, including existing batch,
terminal, fixture and evaluator regressions. The reference passes 73 private
observations and three public tests; seven known faults and the incomplete
baseline fail. `just fmt` and `just fmt-check` passed. No Rust rebuild or
17,000-test workspace run was needed. Historical evaluator modules are unchanged.

Implementation landed as [PR 8](https://github.com/JA-Marshall/codex/pull/8),
[PR 9](https://github.com/JA-Marshall/codex/pull/9),
[PR 10](https://github.com/JA-Marshall/codex/pull/10), and
[PR 11](https://github.com/JA-Marshall/codex/pull/11). Their combined lab tree
matches the frozen complete source. GitHub reported no remote checks.

After human approval, use the frozen `run_batch.py` with the live recommended
manifest, `--jobs 8`, and fresh output at the campaign root's `batch` directory.
Use the existing dedicated credential/home environment without printing secrets.
Record acceptance of proposed edits, exact target decisions and later amendments.
Evaluate terminal candidates with frozen `evaluate_queue.py`; include every
failure and blocked condition in the report. The old ten verifier-only trials
remain separate and unapproved.

No benchmark winner can be inferred from preparation. The incomplete factorial
matrix and shared-plan blocks must be retained in subsequent analysis.
