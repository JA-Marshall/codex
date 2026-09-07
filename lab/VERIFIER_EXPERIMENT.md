# Verifier instruction experiment

Compare the existing `verifier/tests-only-v1` instructions with `verifier/tests-only-single-observation-v2`. The new variant explains the existing host contract: exactly one report entry per verification ID, backed by an actual completed command. Multi-scenario criteria use one aggregate assertion command. The host's verification/evidence rules are unchanged.

Use the previously generated canonical dependency-ordering plan byte-for-byte (`measurement/dependency-order-v1.plan.json`, SHA-256 `0eadb6d14529a2989108b40ffbbb8e44bbca0b0be88e776b8424730c74449a53`). Both conditions use Markdown, the same planner and executor, and the same pinned Muse Contributor model configuration. The new workflow inherits `plan-md-v1` and overrides only its verifier selector. The original verifier module remains unchanged.

Create two fresh isolated fixture checkouts and sealed preparations with the versioned parallel-runner binary. Import the canonical plan in both preparations; neither needs a model call. Verify their resolved run specifications and actual phase-context inputs, instruction pins, clean identical Git baselines and unapproved state. Freeze the batch/evaluator/configuration/catalog/binary/interpreter inputs and record their hashes.

Before implementation, present both fresh exact execution targets for human approval. Approval of the experiment setup does not approve those targets. After approval, execute one attempt per condition concurrently with `--jobs 2`, retaining independent amendment gates. No automatic retries or amendment approvals. Record actual active overlap from batch events and phase/model evidence, not merely the configured job limit.

Independently evaluate each eligible terminal candidate after confirmed shutdown, including failed workflows. Report workflow completion separately from candidate correctness, plus verifier report cardinality, token usage, tool/model calls and wall time. Keep preparation and execution costs separate. The current Rust comparison command only supports renderer experiments; do not pass this pair off as a renderer comparison. Use a separate descriptive control/outcome receipt for this pair.

One observation per condition is a diagnostic, not a reliable improvement estimate. Remote immutable model revision, provider queueing and unrecorded system state remain unknown. There is no new cumulative token/spend cap. Automatic evaluator scheduling, generic comparison dimensions and broader benchmarks are deferred; no runtime, provider or core changes are part of this iteration.
