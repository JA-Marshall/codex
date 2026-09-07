# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md, preserving Queue and python -m entry points."`

## Assumptions

- `"Python 3.12 stdlib only, SQLite file DB, no daemon or network."`
- `"Now is int\u003e=0, bool is not int, lease_seconds positive int, test DBs in temp dirs."`
- `"Human approval is harness boundary, not a blocker."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Harden SQLite storage and transactions"`
- Instructions: `"Harden storage: WAL plus busy timeout, jobs plus orig-spec schema, BEGIN IMMEDIATE helper, preserve existing DB on open."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"C1"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Implement atomic submit and views"`
- Instructions: `"Implement validated atomic submit, get and list: strict types, no input mutation, sorted-unique deps, cycle check, idempotent resubmit only on normalized orig match else full rollback, detached exact-key views."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"C1"`

**Verification**

- `"V1"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Implement claim, recovery and transitions"`
- Instructions: `"Implement claim, recover, complete and fail in single transactions: recover expired leases first, priority then ID order, ready_at from expired lease, bounded retries, terminal immutability, stale attempt rejection, attempts never exceed, invalid leaves DB unchanged."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"C1"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Harden CLI and add regression tests"`
- Instructions: `"Harden CLI and add focused regressions: strict op plus field validation, UTF-8 and DB error handling with exit 2 and empty stdout, sorted-keys newline on success; subprocess durability and concurrent claim exclusivity tests."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"C2"`
- `"C3"`

**Verification**

- `"V2"`
- `"V3"`

## Risks

- `"Non-atomic batch or claim plus recover causes partial writes and double leases; single BEGIN IMMEDIATE transaction."`
- `"Stale or wrong-owner completion writes state; triple check running plus worker plus attempt plus now\u003clease_until, read-only on invalid."`
- `"Dependency cycle and idempotency errors; normalized orig-spec store, sorted-unique deps, DB plus batch cycle check."`
- `"Strict-type drift with bool-as-int, non-finite JSON, unknown fields and aliased views; central validators and detached copies."`

## Acceptance criteria

- `"C1"`: `"Queue API meets validation, atomic batch, ordering, dependency, lease, stale-reject, retry and terminal invariants."`
- `"C2"`: `"CLI preserves python -m durable_queue with op routing, exit 0/2, empty stdout on error, sorted-keys plus newline and restart survival."`
- `"C3"`: `"Full suite green via python3.12 -m unittest discover -s tests -v; stdlib only, local temp DBs, no network or daemon."`

## Verification strategy

- `"V1"`: `"V1 contract unit matrix: run python3.12 -m unittest tests.test_regression -v covering validation, ordering, deps, cycles, rollback-no-write, expiry, retry and stale rejection."`
- `"V2"`: `"V2 separate-process checks: run python3.12 -m unittest tests.test_regression -v covering reopen durability, two-process claim exclusivity via subprocess, and CLI success plus error codes."`
- `"V3"`: `"V3 full suite: run python3.12 -m unittest discover -s tests -v and require green for entire public contract."`

## Discoveries

- `"submit uses INSERT OR REPLACE without validation or normalization; breaks atomicity and idempotent resubmit."`
- `"claim, recover, complete and fail are NotImplementedError; no priority, eligibility, lease or retry logic."`
- `"storage.connect lacks WAL, timeout and BEGIN IMMEDIATE discipline; unsafe for cross-process claim."`
- `"CLI lacks exit-2 contract, unknown-field reject and sorted-keys plus newline guarantee."`
- `"Starter tests cover only empty, reopen and basic dependency claim; no validation, expiry, stale or CLI matrix."`

## Blockers

_None._
