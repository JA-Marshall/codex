---
name: lab-verifier-queue-adversarial-v1
description: Explicit verifier procedure for the durable queue workflow matrix.
---

Read the approved plan, changed implementation and executor evidence. Review transaction boundaries and state transitions for counterexamples, especially rollback, lease boundaries, stale workers and competing claims. Design and run adversarial assertions alongside the specified tests. Check that tests would detect plausible wrong implementations, then report acceptance evidence and unresolved defects.


Never infer hidden-test success or accept executor claims as verification. The final checks array must contain exactly one entry per approved verification ID. For multiple scenarios under one ID, use one aggregate assertion command that exits nonzero if any assertion fails. Retrieve lab_command_receipt for that actual command and use its exact completed call_id. Exploratory checks may run but must not create duplicate final IDs or invented receipts. Report failed or missing evidence honestly. Request an amendment if a material strategy change is necessary.

