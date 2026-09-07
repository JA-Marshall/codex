# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue stdlib package and JSON CLI per CONTRACT.md, with separate-process durability and regression tests."`

## Assumptions

- `"Python 3.12 stdlib only, no network/daemons."`
- `"SQLite file at db_path shared by independent processes."`
- `"Caller supplies integer now; bool is not int."`
- `"Test DBs in temp dirs; preserve Queue and python -m durable_queue."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage and atomic submit/views"`
- Instructions: `"Harden storage WAL/timeout with BEGIN IMMEDIATE txns and spec+state columns; implement strict submit/views: no input mutation, bool!=int/finite-JSON/field checks, atomic batch rollback, idempotent same-spec vs conflict, unknown/self/cycle checks, exact detached views."`

**Affected files**

- `"durable_queue/storage.py"`
- `"durable_queue/queue.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic claim and lease recovery"`
- Instructions: `"Implement validated claim/worker/now/lease_seconds plus recover(now): recover expired leases first under exclusive txn, claim one eligible job by priority then lex-ID, apply bounded-retry ready_at rule, sorted IDs, idempotent no-op, no write on validation error."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Stale-safe complete/fail retries"`
- Instructions: `"Implement complete/fail with strict running/worker/attempt/now\u003clease_until/retry_delay checks, zero writes on error, terminal-state and stale-attempt reject, correct succeeded/pending/failed and ready_at/lease clearing within attempt cap."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"CLI contract and process tests"`
- Instructions: `"Harden CLI op/field whitelist, UTF-8/JSON/object checks, exit-2 empty-stdout, sorted-keys newline exit-0; add test_regression.py and test_processes.py via subprocess+CLI for reopen durability and two-process exclusivity, preserve test_public.py."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`
- `"tests/test_processes.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"A2"`
- `"A3"`

**Verification**

- `"V1"`
- `"V3"`

## Risks

- `"Cross-process double-claim without exclusive BEGIN IMMEDIATE txn."`
- `"Invalid request partially recovering leases or writing."`
- `"Bool/int and finite-JSON confusion; spec-equality vs live state."`
- `"CLI leaking stdout on error or missing exit-2."`

## Acceptance criteria

- `"A1"`: `"Submit/views/claim/recover/complete/fail match CONTRACT incl. validation, atomic rollback, idempotent same-spec, cycles, priority/lex order, leases, bounded retries, stale guards."`
- `"A2"`: `"CLI validates op/fields/UTF-8/JSON, exit 2 empty-stdout on error, sorted-keys newline exit 0, fresh-process durability across restarts."`
- `"A3"`: `"Separate-process claim exclusivity and reopen durability covered by regression tests."`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v; require all green."`
- `"V2"`: `"Run python3.12 -m unittest discover -s tests -v plus contract matrix: invalid batches unchanged, lease/retry/stale paths via python3.12 inline checks."`
- `"V3"`: `"Run python3.12 -m unittest tests.test_processes -v and CLI checks python3.12 -m durable_queue --db PATH --request FILE for success and exit-2 empty-stdout."`

## Discoveries

- `"queue.py submit uses INSERT OR REPLACE, no validation/atomicity/cycles/idempotency."`
- `"claim/recover/complete/fail are NotImplementedError."`
- `"storage.py connect has no WAL/timeout/transaction tuning."`
- `" __main__.py mutates request, no field/op validation or exit-2/sorted-key guarantees."`

## Blockers

_None._
