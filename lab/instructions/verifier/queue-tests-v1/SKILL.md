---
name: lab-verifier-queue-tests-v1
description: Explicit verifier procedure for the durable queue workflow matrix.
---

Read the approved plan and implementation evidence. Run the specified relevant tests and focused acceptance assertions. Inspect failures as needed to explain them. Record exact commands, outcomes and evidence references; explicitly report unavailable or unsupported acceptance checks.


Never infer hidden-test success or accept executor claims as verification. The final checks array must contain exactly one entry per approved verification ID. For multiple scenarios under one ID, use one aggregate assertion command that exits nonzero if any assertion fails. Retrieve lab_command_receipt for that actual command and use its exact completed call_id. Exploratory checks may run but must not create duplicate final IDs or invented receipts. Report failed or missing evidence honestly. Request an amendment if a material strategy change is necessary.

