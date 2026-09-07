# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md with atomicity, leases, retries, rollback and multiprocess regression tests."`

## Assumptions

- `"Python 3.12 stdlib sqlite3 only, manual integer now \u003e=0, tempdir DBs."`
- `"Preserve Queue and python -m durable_queue entry points; no network/daemon/packages/UI."`
- `"Invalid requests raise ValueError with zero writes including no implicit recovery."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage transactions and validators"`
- Instructions: `"Harden storage.py: WAL mode, busy timeout, BEGIN IMMEDIATE txn helper, stable schema preserving jobs, shared strict validators (bool!=int, finite JSON, nonempty id/worker)."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`
- `"AC2"`
- `"AC3"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic submit and views"`
- Instructions: `"Implement atomic submit/get/list: normalize defaults, reject unknown fields, no caller mutation, intra-batch dup, unknown/self/cycle check, idempotent original-spec store, detached 10-key views, ID-sorted list."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC1"`

**Verification**

- `"V1"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Atomic leases and transitions"`
- Instructions: `"Implement claim(+implicit recover)/recover/complete/fail in one exclusive txn: eligibility, priority+lexicographic pick, lease math, ready_at rules, stale/terminal checks, no write on error."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"AC2"`
- `"AC3"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Strict CLI and regression tests"`
- Instructions: `"Rewrite CLI with op/signature whitelist, sorted-keys newline exit0, exit2 empty-stdout on error, fresh-process commit; add local-only tests: multiprocess claim exclusivity, CLI durability, rollback, expiry/retry/stale matrix."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC3"`
- `"AC4"`
- `"AC5"`

**Verification**

- `"V2"`
- `"V3"`

## Risks

- `"Batch partially writes without BEGIN IMMEDIATE; invalid batch must roll back including recovery."`
- `"Concurrent claim double-grants lease without exclusive txn and single-statement claim."`
- `"Stale worker completes/fails after expiry or reclaim; require worker+attempt match and now\u003clease_until, terminal immutable."`
- `"Unready jobs claimed when dependencies merely exist; require all succeeded, failed blocks without propagation."`
- `"Bool accepted as int, non-finite JSON, wrong view keys/order, wrong ready_at rules break contract checks."`

## Acceptance criteria

- `"AC1"`: `"Atomic submit: validation, dedup, unknown/self/cycle rejection, idempotent spec match, zero writes on invalid batch, detached 10-key views, get/list sorted."`
- `"AC2"`: `"Claim/recover/complete/fail state machine: eligibility, priority+lexicographic order, lease math, bounded retries, stale/terminal rejection, no write on ValueError."`
- `"AC3"`: `"Cross-process safety: BEGIN IMMEDIATE claim+recover atomicity, no double active lease, durability across reopen/fresh process."`
- `"AC4"`: `"Strict CLI: op/field whitelist, sorted-keys single newline exit 0, exit 2 empty stdout on all error paths, per-invocation commit."`
- `"AC5"`: `"Local regression suite passes via full unittest discover covering contract matrix plus multiprocess exclusivity and rollback."`

## Verification strategy

- `"V1"`: `"V1 contract matrix: run python3.12 -m unittest discover -s tests -v for validation, ordering, leases, retries, stale rejection."`
- `"V2"`: `"V2 multiprocess safety: run python3.12 -m unittest tests.test_regression -v for subprocess claim exclusivity and fresh-process durability."`
- `"V3"`: `"V3 CLI and rollback: run python3.12 -m unittest discover -s tests -v plus CLI exit-2, sorted-keys newline, invalid-batch zero-write checks."`

## Discoveries

- `"submit uses INSERT OR REPLACE destroying existing jobs, no validation/atomicity/cycles/idempotency."`
- `"claim/recover/complete/fail unimplemented; storage single jobs(id,data) table, timeout 5, no WAL or txn control."`
- `"CLI pops op, direct dispatch, leaks tracebacks, no sorted-keys/newline/exit-2/field-whitelist handling."`

## Blockers

_None._
