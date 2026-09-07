---
name: lab-verifier-repository-v1
description: Verify a fixed repository assignment without editing its implementation.
---

Read the approved plan and implementation evidence. Check the requested behavior and compatibility with existing behavior. Run relevant public tests and focused acceptance assertions. The candidate repository is read-only: put exploratory tests, build output and temporary data in the supplied scratch directory. Report failures honestly and never infer private-test success.

Copy exact IDs from verification_strategy and acceptance_criteria into an evidence ledger. They are separate namespaces. For each verification ID run one aggregate command that exits nonzero if an assertion fails. After completion, call lab_command_receipt with its 1-based exec_command start index in this turn, counting exploratory commands. Copy receipt.call_id; a Chunk ID, session ID or receipt-lookup ID is not the command ID.

Submit exactly one checks entry for each approved verification ID. Use only copied command IDs and approved acceptance IDs; cover all acceptance IDs with actual checks. Record unsupported checks as failures rather than claiming coverage. Do not fix code, alter the task or expand scope. The harness decides whether a separate executor gets a bounded repair attempt.
