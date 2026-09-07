# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md, preserving Queue and python -m durable_queue entry points, with separate-process durability and exclusivity tests."`

## Assumptions

- `"Python 3.12 stdlib only; no network, packages, daemon or UI."`
- `"No wall clock: now int\u003e=0, lease_seconds/retry_delay ints with strict ranges; bools never valid ints."`
- `"Each Queue(db_path) call is fresh process-safe SQLite handle; test DBs in temp dirs."`

## Implementation steps

### Step `"IMP-1"`

- ID: `"IMP-1"`
- Title: `"Durable storage transaction foundation"`
- Instructions: `"Add WAL, busy_timeout, BEGIN IMMEDIATE txn helper and normalized columns/indexes for atomic claim; preserve existing DB files via compat or migration."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC-2"`
- `"AC-3"`

**Verification**

- `"VER-1"`
- `"VER-2"`

### Step `"IMP-2"`

- ID: `"IMP-2"`
- Title: `"Atomic submit and detached views"`
- Instructions: `"Implement strict submit/views: no input mutation, sorted-unique deps, batch dup/unknown/self/cycle checks, idempotent same-spec vs conflict reject, single-txn insert, exact detached views."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"IMP-1"`

**Acceptance criteria**

- `"AC-1"`
- `"AC-5"`

**Verification**

- `"VER-1"`

### Step `"IMP-3"`

- ID: `"IMP-3"`
- Title: `"Atomic claims and lease transitions"`
- Instructions: `"Implement single-txn claim with expiry recovery plus recover/complete/fail with strict worker/attempt/lease checks, priority/ID order, bounded max_attempts and retry_delay, no-write on ValueError."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"IMP-2"`

**Acceptance criteria**

- `"AC-2"`
- `"AC-3"`

**Verification**

- `"VER-1"`
- `"VER-2"`

### Step `"IMP-4"`

- ID: `"IMP-4"`
- Title: `"Strict CLI and regression tests"`
- Instructions: `"Harden CLI op/field whitelist, UTF-8/JSON/object checks, exit-2 empty-stdout on error, sorted JSON newline on success; add regression tests with multiprocessing and subprocess durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"IMP-3"`

**Acceptance criteria**

- `"AC-4"`
- `"AC-5"`

**Verification**

- `"VER-1"`
- `"VER-3"`

## Risks

- `"Cross-process double-claim without BEGIN IMMEDIATE and indexed normalized columns."`
- `"Invalid batch must fully rollback including no implicit expiry recovery or partial writes."`
- `"Strict bool/finite-JSON, priority/ID ordering, ready_at=expired lease_until vs failed-terminal, and CLI canonical sorted JSON."`

## Acceptance criteria

- `"AC-1"`: `"Submit/views atomic, validated, idempotent on normalized original spec, exact 10-key detached views; get/list validate IDs with no implicit recovery."`
- `"AC-2"`: `"Claim validates inputs, recovers expired leases first, atomically claims one eligible job by priority then ID; no shared active lease across processes."`
- `"AC-3"`: `"Recover/complete/fail enforce lease_until, worker, attempt, max_attempts and retry_delay semantics; invalid requests raise ValueError with no write or recovery."`
- `"AC-4"`: `"CLI preserves Queue and python -m durable_queue; success exit 0 single sorted-keys JSON plus newline, all failures exit 2 empty stdout; DB survives restarts."`
- `"AC-5"`: `"Focused regression tests cover rollback, stale completion, bounded retries, separate-process durability and exclusivity; python3.12 -m unittest discover -s tests -v passes."`

## Verification strategy

- `"VER-1"`: `"Run python3.12 -m unittest discover -s tests -v covering submit/views/claim/recover/complete/fail and validation rollback matrix."`
- `"VER-2"`: `"Run python3.12 -m unittest tests.test_regression -v verifying reopen durability, two real processes never share active lease, expired lease re-pends."`
- `"VER-3"`: `"Run CLI subprocess checks with python3.12 -m durable_queue --db PATH --request FILE: success exit 0 canonical JSON, failures exit 2 empty stdout."`

## Discoveries

- `"queue.py submit unvalidated with INSERT OR REPLACE, mutates semantics, no cycle/atomic/idempotent/detached-copy logic."`
- `"claim/recover/complete/fail raise NotImplementedError; storage.py single JSON blob table without WAL/timeout/txn helper."`
- `"__main__.py pops op without whitelist, no UTF-8/object/field validation, no exit-2 empty-stdout handling."`
- `"tests/test_public.py covers only empty, reopen, claim-dependency-complete happy paths."`

## Blockers

_None._
