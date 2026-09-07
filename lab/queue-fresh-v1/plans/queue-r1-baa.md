# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md with atomic cross-process semantics and regression tests."`

## Assumptions

- `"Python 3.12 stdlib only, no network/packages/daemon/UI"`
- `"SQLite file DB with integer now, no wall clock"`
- `"Queue and python -m durable_queue entry points frozen"`
- `"Test DBs in temporary directories"`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage transactions and atomic submit"`
- Instructions: `"Harden storage: WAL, busy timeout, BEGIN IMMEDIATE txn helper. Store normalized spec plus live view. Implement strict submit validation, batch dup/cycle/unknown/self checks, idempotent same-spec else reject, atomic commit/rollback without implicit recover, no input mutation."`

**Affected files**

- `"durable_queue/storage.py"`
- `"durable_queue/queue.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic claim and lease recovery"`
- Instructions: `"Implement recover(now) and claim(worker,now,lease_seconds) in one IMMEDIATE txn each: validate ints, recover lease_until\u003c=now with ready_at/exhaustion rules, then claim single eligible job ordered by priority/id, set running/attempts/worker/lease."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"A2"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Stale-safe complete and bounded fail"`
- Instructions: `"Implement complete/fail with strict validation (running, owner, positive attempt match, now\u003clease, retry_delay int\u003e=0), zero writes on reject, clear lease, succeeded vs pending-with-backoff vs failed-on-exhaustion, attempt cap enforcement."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"A3"`

**Verification**

- `"V1"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Strict CLI and regression tests"`
- Instructions: `"Harden CLI: strict op/field whitelist, fresh Queue per invocation, sorted-keys single-line exit-0, exit-2 empty-stdout on ValueError/malformed/UTF-8/missing/usage/DB error. Add test_regression.py and test_processes.py for rollback, stale/expired, retries, deps, subprocess exclusivity and reopen durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`
- `"tests/test_processes.py"`

**Dependencies**

- `"S1"`
- `"S2"`
- `"S3"`

**Acceptance criteria**

- `"A4"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Cross-process double-claim without BEGIN IMMEDIATE + single-txn recover+claim"`
- `"Invalid batch partially committing including implicit recovery side effects"`
- `"Stale/wrong-owner/expired complete/fail writing state"`
- `"Recovery ready_at must be expired lease_until vs unchanged on exhaustion; bool-as-int and non-finite JSON acceptance"`

## Acceptance criteria

- `"A1"`: `"Submit validates fields/types/cycles atomically; idempotent only on normalized original-spec match; views exact keys/detached/sorted; get/list validate without implicit recover."`
- `"A2"`: `"Claim validates then recovers expired leases in same txn, claims one eligible job by priority/id, bumps attempts/lease; never double-leases across processes; failed deps stay ineligible."`
- `"A3"`: `"Complete/fail require running+owner+attempt+now\u003clease with no side-recover/write on reject; clear lease; correct terminal/retry_delay/cap; reject stale attempts."`
- `"A4"`: `"CLI strict op/field whitelist, sorted-keys+newline exit-0, exit-2 empty-stdout on any error; fresh-process durability; stdlib-only temp-dir tests pass via unittest discover."`

## Verification strategy

- `"V1"`: `"V1 contract matrix: run python3.12 -m unittest discover -s tests -v plus targeted checks for validation, ordering, leases, retries, idempotency."`
- `"V2"`: `"V2 separate-process durability/exclusivity: run python3.12 -m unittest tests.test_processes -v covering concurrent claimants and kill/restart reopen."`
- `"V3"`: `"V3 CLI roundtrips: run python3.12 -m unittest discover -s tests -v and manual python3.12 -m durable_queue --db PATH --request FILE success/error exit-code checks."`

## Discoveries

- `"queue.submit uses INSERT OR REPLACE: clobbers state, no validation/atomicity/cycle/idempotency/detach handling"`
- `"claim/recover/complete/fail unimplemented; storage.connect has no WAL/BEGIN IMMEDIATE/timeout discipline"`
- `"__main__ lacks exit-2/unknown-field/sorted-keys/newline handling; tests/test_public.py covers happy path only"`

## Blockers

_None._
