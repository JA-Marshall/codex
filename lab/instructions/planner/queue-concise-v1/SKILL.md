---
name: lab-planner-queue-concise-v1
description: Explicit planner procedure for the durable queue workflow matrix.
---

Read TASK.md, CONTRACT.md, repository instructions and relevant implementation. Identify the smallest complete repair of the public API and CLI. Produce a concise canonical plan grounded in the actual files. Prioritize direct implementation steps and specific acceptance checks; avoid optional abstractions and unrelated cleanup.

Return a canonical plan for validation and human review; do not implement. Use at most four concise implementation steps and three aggregate verification items, with stable IDs and valid references. Include the schema's required assumptions, affected files, dependencies, risks, acceptance criteria, discoveries and blockers without repeating the contract. Human approval is a harness boundary, not an unresolved task blocker. Keep prose compact enough for the existing phase context limits. The harness chooses presentation independently of this procedure.

