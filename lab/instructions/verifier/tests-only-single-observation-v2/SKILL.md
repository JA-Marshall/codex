---
name: lab-verifier-tests-only-single-observation-v2
description: Verify approved acceptance criteria with tests for an explicitly assigned lab verifier role.
---

Read the approved canonical plan and implementation evidence. Run the specified
relevant tests under repository instructions and record exact commands, outcomes,
and evidence references. Report failures, unavailable checks, and acceptance
criteria without supporting evidence explicitly. Never infer hidden-test success
from visible tests or infer task success solely from an executor's completion
message. Request an amendment when verification requires a material strategy change.

The final checks array must contain exactly one entry for each verification ID
in the approved plan. Do not duplicate an ID to report its individual scenarios.
For a criterion covering several scenarios, run one aggregate assertion command
that checks all required scenarios and exits nonzero if any assertion fails.
For example, invalid-input CLI scenarios should assert the expected exit code
and empty stdout inside that aggregate command; the aggregate itself succeeds
only when every assertion passes. Do not discard failures or make an aggregate
succeed unconditionally.

Retrieve lab_command_receipt for that actual aggregate command and use its exact
completed call_id in the single check entry. A normal test-suite command can be
the single observation when it covers the whole verification criterion. Other
exploratory commands may run, but do not add duplicate final check entries or
invent receipts. If required evidence is missing or fails, report the failure;
never claim successful verification merely to satisfy the report shape.
