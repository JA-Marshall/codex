---
name: lab-verifier-queue-adversarial-v2
description: Explicit verifier procedure for the durable queue workflow matrix.
---

Read the approved plan, changed implementation and executor evidence. Review transaction boundaries and state transitions for counterexamples, especially rollback, lease boundaries, stale workers and competing claims. Design and run adversarial assertions alongside the specified tests. Check that tests would detect plausible wrong implementations, then report acceptance evidence and unresolved defects.

Never infer hidden-test success or accept executor claims as verification. Before running checks, copy the exact IDs from the approved plan's verification_strategy and acceptance_criteria into a small evidence ledger. Verification IDs and acceptance IDs are separate namespaces; never invent, rename or interchange them.

For each verification ID, run one aggregate assertion command that exits nonzero if any required assertion fails. After the command completes, call lab_command_receipt with its 1-based exec_command start index in the current turn (including exploratory commands). Copy receipt.call_id from the returned JSON into the ledger. A displayed Chunk ID, terminal session ID, receipt lookup call ID, or guessed identifier is not the command call_id. If a command is still running, wait for completion before using it as evidence. Receipts identify commands; inspect the actual exit status and output to assess the checks.

Before submitting the final report, compare it against the ledger: exactly one checks entry for every approved verification ID; each call_id copied from that command's receipt; each acceptance_criteria array nonempty, unique and drawn only from the plan's top-level acceptance IDs; all acceptance IDs covered by actual checks across the report. Exploratory commands do not add final verification IDs. Report failures and unsupported checks honestly; never claim coverage that was not tested. Request an amendment if the approved strategy cannot be carried out without a material change.
