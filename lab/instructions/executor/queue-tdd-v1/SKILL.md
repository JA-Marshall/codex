---
name: lab-executor-queue-tdd-v1
description: Explicit executor procedure for the durable queue workflow matrix.
---

Follow the approved canonical plan using a test-first procedure. For each approved behavior, first add a focused test that fails for the intended missing behavior, run it and record the failure; then implement the smallest change that passes it. Refactor only within approved scope while keeping tests green. Include interactions between persistence, leases and dependencies in this cycle. Record red/green evidence and remaining limitations for the verifier.


Preserve stable step IDs. If new information materially invalidates the approved strategy, scope, dependencies or acceptance criteria, request an amendment and stop until the harness provides authority. Instructions guide procedure; the harness controls admission.

