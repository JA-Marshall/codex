# Bounded verification repair

Set `max_repairs = 2` on a workflow to permit up to two repair rounds after the
initial implementation. The setting inherits normally, can be overridden with
zero, and accepts values from zero through four. Omitted/zero preserves the
one-pass workflow and its serialized configuration shape. A nonzero setting is
part of the effective RunSpec and therefore the exact human approval target.

The sequence is approved implementation, verification, then (only if a valid
report cites failed host-observed commands) repair and fresh verification. Each
repair uses the same executor instructions and approved canonical plan. The
executor receives bounded failed verification IDs and diagnoses those checks in
the candidate repository. Hidden evaluator answers/results never enter this loop.
All approved steps and all verification criteria require fresh evidence after
each repair; previous success cannot establish success for the repaired candidate.

The domain state machine enforces the repair budget across the whole run, including
amendments. A repair returns from verifying to implementing under the same exact
approval. A material plan change still revokes authority and requests an amendment;
repair does not approve it. Runtime failure, failed shutdown, invalid reports,
missing command receipts and verifier-only replay are not automatic repair paths.
Existing phase, context and sandbox limits remain. Preparation reserves room for
repair feedback inside the existing prompt limit and refuses oversized plans.

The workflow journal records failed checks before each repair and a numbered
`repair_started` transition. Phase artifacts retain commands, results, model usage
and shutdown evidence. Repair-enabled runs also record `verification-NN.json` and
`verification-NN.diff` at each valid verification round, plus `repair-NN.json` for
admitted repairs. Final successful metrics include `repair_attempts`; failed runs
retain their journal and phase evidence, including exhausted budgets. These are
within-trial repairs, not replacement trials or hidden retries.

Passing verifier commands still depends on test quality. A missed bug will not
trigger repair, and a repair may fail or request an amendment. Independent evaluation
must score final candidates separately from workflow completion. Compare initial
and final checkpoints and total tokens when studying repair effectiveness.

The queue repair catalog selects two repairs for all eight role combinations.
The next requested campaign has 32 trials at concurrency 16: four executions per
combination, importing each of the first two existing plan blocks twice. This
preserves four canonical plans without replacing the earlier failed planner sample.
It provides execution repetitions, not four independent planner samples per role.
The prior sixteen-target v2 packet is superseded and remains unlaunched.
