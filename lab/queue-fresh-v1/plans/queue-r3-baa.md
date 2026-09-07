# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue Python package and JSON CLI per CONTRACT.md preserving Queue and python -m durable_queue entry points."`

## Assumptions

- `"Python 3.12 stdlib and sqlite only; no network, daemon, external packages, or UI."`
- `"Logical now integer \u003e=0 and lease_seconds positive integer; bool never valid as int."`
- `"Queue(db_path) creates and preserves SQLite file; test DBs in temp dirs; entry points preserved."`
- `"Invalid requests raise ValueError with zero DB writes including no implicit recovery."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage transactions and schema"`
- Instructions: `"Add BEGIN IMMEDIATE txn contextmanager, WAL journal_mode plus busy_timeout, jobs state table plus immutable normalized spec table preserving original payload/priority/deps/max_attempts/ready_at."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Submit and views"`
- Instructions: `"Implement submit/get/list validators: exact allowed fields, finite JSON, int checks rejecting bool, sorted-unique deps, full pre-write cycle/unknown/self/duplicate/conflict checks, single-txn atomic batch, detached copies without caller mutation."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC2"`

**Verification**

- `"V1"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Claims and transitions"`
- Instructions: `"Implement claim with upfront validation then one txn recovering expired leases plus priority/ID select and conditional running update; recover mapping to pending/failed; complete/fail with running+worker+attempt+now\u003clease checks and zero writes on error."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"AC3"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"CLI and regression tests"`
- Instructions: `"Harden CLI to strict op and per-op fields, UTF-8/missing/DB handling with exit 2 and empty stdout plus sorted-keys newline on success; add focused regressions including multiprocessing submit-survives-restart and concurrent claim exclusivity."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC4"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Lost-update and double-claim without single BEGIN IMMEDIATE recovery-plus-claim transaction."`
- `"Invalid batch leaking partial writes or recovery side-effects on validation failure."`
- `"bool-as-int, non-finite JSON, caller mutation, or stdout pollution breaking validation and CLI contract."`

## Acceptance criteria

- `"AC1"`: `"Atomic durable storage: BEGIN IMMEDIATE txn helper, WAL+timeout, spec/state split preserves jobs across reopen."`
- `"AC2"`: `"submit/get/list: strict validation, sorted-unique deps, cycle/unknown/self check, atomic batch, idempotent resubmit, exact detached views."`
- `"AC3"`: `"claim/recover/complete/fail: priority/ID order, expired-lease recovery, bounded retries, terminal states, stale/expired rejection with zero side-effects, no double-claim."`
- `"AC4"`: `"CLI plus regressions green: strict op/fields, sorted-keys newline exit 0/2, multiprocess durability/exclusivity via python3.12 -m unittest discover -s tests -v."`

## Verification strategy

- `"V1"`: `"V1 contract matrix: run python3.12 -m unittest discover -s tests -v covering validation, atomicity, ordering, leases, retries, terminal states."`
- `"V2"`: `"V2 multiprocess durability: run python3.12 -m unittest discover -s tests -v with separate-process submit-survives-restart and concurrent claim exclusivity tests."`
- `"V3"`: `"V3 CLI contract: run python3.12 -m durable_queue --db PATH --request FILE success shape checks plus python3.12 -m unittest discover -s tests -v for all exit-2 paths."`

## Discoveries

- `"storage.py single jobs(id,data) table with INSERT OR REPLACE; no spec split, no BEGIN IMMEDIATE, WAL, or timeout tuning."`
- `"queue.py submit/get/list naive without validation/normalization/cycle/idempotency/rollback; claim/recover/complete/fail NotImplementedError."`
- `"__main__.py no op allowlist or strict fields, mutates request, no sorted-keys newline or exit-2 handling for bad JSON/UTF-8/missing/DB/ValueError."`
- `"tests/test_public.py three happy-path tests only; no invalid-batch, lease, stale-worker, retry, CLI, or multiprocess coverage."`

## Blockers

_None._
