# Two verifier conditions ready for approval

Both preparations are unapproved. No execution host or model phase has started.
The imported plan required zero model calls. Approving this pair authorizes one
attempt per condition in parallel with `--jobs 2`, followed by independent
evaluation and a descriptive comparison. Any plan amendment needs a new decision.

## Concrete implementation scope

Both runs implement the same dependency-ordering fixture from clean commit
`8e166376f2a0a057c828d33d7fee32170ab136b4`, in separate checkouts:

1. `s1`: implement validation and lexicographic Kahn ordering in `dependency_order.py`.
2. `s2`: fix `cli.py` error handling, UTF-8 input and exact output/exit behavior.
3. `s3`: add `tests/test_regression.py` covering ordering, invalid input, cycles,
   duplicate dependencies, input immutability and CLI behavior.

Verification IDs are `v-unittest` and `v-cli`. The unittest command runs only this
small isolated fixture's tests, not the Codex workspace suite. Review the full
[rendered plan](PLAN.md) or its source-of-truth [canonical JSON](plan.json).

## Controlled difference

| Condition | Workflow | Verifier |
| --- | --- | --- |
| Existing | `plan-md-v1` | `verifier/tests-only-v1` |
| Explicit report contract | `plan-md-single-observation-v2` | `verifier/tests-only-single-observation-v2` |

The [new instructions](../instructions/verifier/tests-only-single-observation-v2/SKILL.md)
require exactly one final check entry per verification ID and one actual command
receipt per check. Multi-scenario criteria use an aggregate command that fails
if any assertion fails. Host verification rules are unchanged.

Canonical plan bytes, Markdown bytes, Muse Contributor model/configuration,
planner, executor, repository baseline and effective harness settings match.
Full resolved RunSpecs differ only at the seven verifier-related selector,
inheritance and instruction fields listed in [preparation.json](preparation.json).

## Exact approval targets

Both targets use plan ID `task-plan`, revision `1`, canonical content SHA-256
`0eadb6d14529a2989108b40ffbbb8e44bbca0b0be88e776b8424730c74449a53`.

| Execution run ID | Effective run-spec SHA-256 |
| --- | --- |
| `verifier-v1-execution` | `14ba875e066ffdce03df13d494c7a83bbf4cd3006a500ed0e2765e4c6627b3e5` |
| `verifier-single-v2-execution` | `d13619e47c519b9a3ee16ba52fc070eab395b4d9ad7da23e44f3fb5c988b1483` |

[Machine-readable targets](review-targets.json) record the complete tuples.
Publishing this packet does not grant human approval. At launch, compare each
fresh live review request against its entire target before submitting a decision.
Do not reuse an old run's approval or retry either execution automatically.

## Validation and resumption

Both real `prepare --plan-file` invocations exited successfully, with zero model
tokens, zero phase threads, empty runtime traces and no approval event. Checked
every sealed preparation hash, frozen inputs, binary/bwrap/interpreter pins,
instruction content hashes and clean identical baselines. Batch preflight accepts
the two isolated repositories and new execution destinations. `just fmt` and
`just fmt-check` passed. This instruction/configuration change needs no Rust test
rerun; the 17,000-test suite was not run.

Frozen experiment root:
`/home/james/.cache/codex-lab-verifier-pilot/20260907T153300Z`.
Use its `inputs/lab/experiments/run_batch.py` and `batch-input.json`, with `--jobs 2`
and fresh output `batch/`, only after the two human decisions. The published
[batch manifest](batch-input.json) is an exact copy. Keep the existing credentials
local; recheck configuration and binary pins before launch. Do not rerun the
collision-refusing preparation/export helpers.

After both hosts stop, use the frozen evaluator on each eligible terminal run,
including failed workflows. Report candidate correctness separately from workflow
completion and inspect verifier cardinality. Establish actual overlap using batch
and phase/model timestamps. Keep costs and outcomes per condition. The existing
renderer-only comparison CLI does not support this dimension; produce a separate
descriptive receipt without changing the runtime.

One run each is diagnostic evidence, not a reliable estimate of improvement.
The remote immutable model revision is unavailable; no cumulative token/spend
cap has been added. See the [experiment plan](../VERIFIER_EXPERIMENT.md).
