# Queue workflow matrix v2: sixteen fresh trials

**Prepared, awaiting human execution approval.** Sixteen isolated clean checkouts,
eight combinations with two plan blocks, concurrency **16**, one attempt per target.
No model calls or tokens were used for these imported-plan preparations. No execution
host has been started. Approval of the previous campaign does not authorize these targets.

## Changes and controls

- Evaluator `durable-queue-v2` promotes the audited JSON serialization validator.
  It accepts valid Unicode escaping and compact/pretty spacing while enforcing
  sorted unique keys, finite JSON, one value and a final newline. The private
  corpus and expected answers are unchanged. Fingerprints include the parser;
  manifests with the old evaluator are rejected. The prior frozen evaluator and
  results remain in their original campaign and Git history.
- Both new verifier variants use the same explicit evidence-ledger procedure:
  exact verification and acceptance IDs, `receipt.call_id` instead of Chunk ID,
  and a final coverage check. Their focused versus adversarial procedures remain
  distinct. Planner/executor instruction bytes are unchanged. No hidden-test hints
  were added, and no benchmark candidate was repaired.
- Reuse the first two prior plan blocks, selected by block order rather than
  candidate success. This includes the accepted corrections to the architecture
  plans. The four canonical plans are byte-identical to their prior preparations.
  These are repeated executions of existing plans, **not new planner samples**.
- Hold Muse `muse-spark-1.3-contributor`, provider/config/catalog, task baseline
  `689b3bd49dd3ef4f746481e909edfad041ab16b0`, frozen runtime binary, renderer,
  context/phase limits, planner and executor constant. Runtime source is unchanged;
  the prior versioned binary is reused. No Codex core or scheduler change.
- Concurrency increases from eight to sixteen. Within this campaign all combinations
  share that limit; old/new timing or pass-rate differences cannot be attributed
  solely to the report instructions. Provider queueing and resource contention are
  outcomes to record, not proof of sixteen simultaneous backend computations.

## Exact execution scope

Letters select planner/executor/verifier: planner A concise, B architecture/risk-first;
executor A conservative/minimal-diff, B TDD; verifier A focused, B adversarial.

| Combination | Block 1 target | Block 2 target |
| --- | --- | --- |
| AAA | queue-v2-r1-aaa-execution | queue-v2-r2-aaa-execution |
| AAB | queue-v2-r1-aab-execution | queue-v2-r2-aab-execution |
| ABA | queue-v2-r1-aba-execution | queue-v2-r2-aba-execution |
| ABB | queue-v2-r1-abb-execution | queue-v2-r2-abb-execution |
| BAA | queue-v2-r1-baa-execution | queue-v2-r2-baa-execution |
| BAB | queue-v2-r1-bab-execution | queue-v2-r2-bab-execution |
| BBA | queue-v2-r1-bba-execution | queue-v2-r2-bba-execution |
| BBB | queue-v2-r1-bbb-execution | queue-v2-r2-bbb-execution |

The complete five-field authority tuples are in [review-targets.json](review-targets.json).
The [batch manifest](batch-input.json) SHA-256 is
`e11a66d8dbfdf89fb50ce40de661723bda2119e1ca30b08464c95de829d52b04`.
Approval covers these sixteen exact targets once, concurrency sixteen, followed by
independent evaluation and publication. It does not approve automatic retries,
plan amendments, repairs, the superseded targets, or the ten older verifier replays.

Read the unchanged plans:
[block 1 concise](plans/queue-r1-aaa.md),
[block 1 architecture](plans/queue-r1-baa.md),
[block 2 concise](plans/queue-r2-aaa.md),
[block 2 architecture](plans/queue-r2-baa.md).
Canonical JSON files sit alongside each Markdown view.

## Validation and resumption

Seven focused evaluator tests passed, including the real sandbox serialization
regression, full reference corpus, real two-process claims, known mutants and
unimplemented baseline. Formatting checks passed afterward; no full workspace
suite or post-format test rerun. Instruction/catalog hashes and effective RunSpecs
were checked during preparation: only profile identity, archive paths and verifier
selection/content differ from each corresponding prior condition. All sixteen
preparations have zero phase threads, empty runtime traces, no approvals, matching
sealed artifact inventories and clean task baselines. Preflight accepts sixteen
distinct checkouts and fresh output destinations at jobs=16.

Campaign root: `/home/james/.cache/codex-lab-queue-matrix/20260907T180348Z-v2`.
Frozen source: `192b8eddcb9555679482bf2caa82b84b0dfb9c36`.
[Preparation receipt](preparation.json), [effective conditions](conditions.json),
[frozen inputs and controls](matrix.json), [preflight](preflight.json).
The preparation helper is archived as `prepare.py.txt`; it refuses collisions and
must not be rerun against this packet. Credentials were not needed for preparation.

After a real human decision, validate every frozen pin and preparation again, launch
the frozen `lab/experiments/run_batch.py` with `--jobs 16` and a new batch directory,
and match each live review request to its newly approved exact tuple. Record a new
approval receipt; never load historical approvals as authority. Let failures and
amendments stop independently without retries. After all hosts and phase threads
exit, run the frozen v2 evaluator on every candidate and preserve all outcomes,
diffs, token/context metadata, protocol failures and timing evidence.

For planning purposes, the prior batch averaged roughly 1.31M execution tokens per
trial: sixteen similar runs would be about 21M tokens, including cached input. This
is an estimate, not a hard cap or a dollar-cost estimate. Existing per-phase limits
remain; the runner has no hard cumulative token/spend cap. Do not spend tokens merely
to reach a target. Report this campaign separately and retain the original scores.
