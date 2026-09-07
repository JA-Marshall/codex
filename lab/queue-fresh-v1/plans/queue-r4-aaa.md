# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md with preserved entrypoints, atomic durability, and focused regression tests."`

## Assumptions

- `"A1 Python 3.12 stdlib only; no network, packages, daemon or UI."`
- `"A2 now/ready_at/lease_until/retry_delay are int\u003e=0 and bool is not int; lease_seconds positive int."`
- `"A3 Test DBs in temp dirs; each CLI call is fresh process on same SQLite file."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Validation and atomic submit"`
- Instructions: `"Add strict submit validation, normalize deps sorted-unique, check dup/unknown/self/cycle, idempotent same original-spec resubmit, whole-batch rollback in single transaction with WAL/timeout; fix storage commit/locking."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`

**Verification**

- `"V2"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic claim and recovery"`
- Instructions: `"Implement recover(now) and claim(worker,now,lease_seconds) with prior recovery in one transaction, priority/lexicographic choice, single UPDATE-guarded ownership, attempts\u003cmax and dependency-succeeded eligibility."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC2"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Stale-safe finish"`
- Instructions: `"Implement complete/fail with running+owner+attempt+now\u003clease_until checks, no recovery/write on invalid, lease clearing, succeeded/pending+ready_at and failed rules, terminal immutability."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"AC3"`

**Verification**

- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"CLI and regression tests"`
- Instructions: `"Harden CLI op/field validation, sorted-keys JSON exit 0, exit 2 empty stdout on all failures; add subprocess durability/exclusivity, batch-rollback, lease/retry/stale/CLI regression tests."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC4"`

**Verification**

- `"V1"`
- `"V3"`

## Risks

- `"SQLite cross-process claim race without BEGIN IMMEDIATE/WAL guarded UPDATE."`
- `"bool versus int and NaN/Infinity finite-JSON strictness."`
- `"Cycle/idempotency versus ready_at mutation and recovery side-effects on invalid paths."`

## Acceptance criteria

- `"AC1"`: `"Submit validates strict types/finite JSON/no mutation, normalizes deps, rejects dup/unknown/self/cycle, idempotent same-spec resubmit, whole-batch atomic rollback with no implicit recovery on invalid."`
- `"AC2"`: `"Claim recovers expired leases then atomically claims single eligible job by priority/lexicographic order; recover resets to pending with ready_at=expired lease or failed; separate processes never share active lease; attempts never exceed max."`
- `"AC3"`: `"Complete/fail require running+owner+attempt match+now\u003clease_until, no write/recovery on invalid, clear lease, succeeded/pending+ready_at or failed rules, terminal immutability, stale-attempt rejection."`
- `"AC4"`: `"CLI validates op/fields, sorted-keys single-line JSON exit 0, all failures exit 2 empty stdout, survives restarts; entrypoints preserved; new subprocess durability/exclusivity plus rollback/lease/retry/stale/CLI regression tests pass."`

## Verification strategy

- `"V1"`: `"V1 full suite: run python3.12 -m unittest discover -s tests -v including new multiprocess claim-exclusivity and reopen-durability tests."`
- `"V2"`: `"V2 contract matrix via API and CLI: run python3.12 -c API checks plus python3.12 -m durable_queue --db PATH --request FILE for submit/views/idempotency/cycles, claim ordering/eligibility, recover, complete/fail stale/expiry/terminal/retry_delay; invalid raises ValueError with DB unchanged."`
- `"V3"`: `"V3 CLI robustness: run python3.12 -m durable_queue --db PATH --request FILE with malformed/unknown-op/unknown-field/bad-UTF8/missing-file/DB-error expecting exit 2 empty stdout, and success expecting sorted-keys JSON newline exit 0 with persistence across restarts."`

## Discoveries

- `"F1 queue.py submit is unvalidated INSERT OR REPLACE mutating semantics; claim/recover/complete/fail raise NotImplementedError."`
- `"F2 storage.py single JSON-blob table with no commit/WAL/timeout/locking discipline for cross-process atomicity."`
- `"F3 __main__.py has no op/field validation, no exit-2 contract, no DB-error handling."`
- `"F4 tests/test_public.py has only 3 starter tests; no subprocess, rollback, lease, or CLI coverage."`

## Blockers

_None._
