# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI with atomic durable transitions and regression tests, preserving Queue and python -m durable_queue entry points."`

## Assumptions

- `"Python 3.12 stdlib only, no network packages daemon or UI."`
- `"now is logical int clock; SQLite file is source of truth."`
- `"Schema may change but existing jobs(id,data) rows are migrated."`
- `"Implementation waits for explicit human approval."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Harden SQLite storage boundary"`
- Instructions: `"Harden storage.py: WAL, busy timeout, transaction() with BEGIN IMMEDIATE commit rollback; migrate legacy jobs(id,data) rows; add normalized columns or spec plus state blobs to support atomic claim and rollback."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`
- `"AC2"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic submit and views"`
- Instructions: `"Implement strict validators and atomic submit plus get list: bool-is-not-int, finite JSON, allowed fields, no caller mutation, sorted-unique deps, reject dup unknown self cycle, idempotent only on exact original-spec match, detached 12-key views sorted by ID."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC1"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Atomic claims and transitions"`
- Instructions: `"Implement claim recover complete fail each in one exclusive txn: recover-then-claim, priority then ID order, dep-succeeded and attempts gate, claim bumps attempts, recover sets ready_at to expired lease_until or failed, strict owner attempt expiry checks with no side effects on error."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"AC2"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Strict CLI and regression tests"`
- Instructions: `"Implement strict CLI and regression tests: UTF-8 object, known op fields only, sorted-keys newline exit 0, exit 2 empty stdout on error; add tmpdir tests for subprocess durability, concurrent-claim exclusivity, rollback, stale retry and dep matrix."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC3"`
- `"AC4"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Double-claim across processes without BEGIN IMMEDIATE exclusive transaction."`
- `"Stale attempt reuse after reclaim by same worker."`
- `"Invalid batch partial write without single-transaction rollback."`
- `"Expired lease_until reused for ready_at and NaN Infinity payloads."`
- `"CLI stdout pollution breaking exit-2 empty-stdout rule."`

## Acceptance criteria

- `"AC1"`: `"Atomic submit with detached 12-key views sorted by ID; invalid batch leaves DB unchanged."`
- `"AC2"`: `"Cross-process atomic claim, expired-lease recovery, bounded retries, stale and terminal rejection."`
- `"AC3"`: `"Strict JSON CLI with sorted-keys output, exit 0 success and exit 2 empty-stdout failures; work survives restarts."`
- `"AC4"`: `"Local regression suite green including subprocess durability and claim exclusivity in tmpdir DBs."`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v; require green starter plus new regression tests."`
- `"V2"`: `"Run python3.12 -m unittest discover -s tests -v -k contract plus targeted CLI checks: python3.12 -m durable_queue --db TMP --request REQ; verify invalid batches unchanged, stale and retry rules."`
- `"V3"`: `"Run python3.12 -m unittest discover -s tests -v -k subprocess and CLI goldens; verify separate-process claim exclusivity, kill-restart durability, exit 0 versus 2 cases."`

## Discoveries

- `"storage.connect single blob table with no commit or exclusive-txn discipline."`
- `"Queue.submit uses INSERT OR REPLACE with no validation atomicity cycle or idempotency check."`
- `"claim recover complete fail are NotImplementedError."`
- `"CLI lacks exit-2 contract and leaks tracebacks to stdout."`
- `"Invariants needed: bool is not int, normalized spec for idempotency, detached views, terminal immutability, no implicit recover on get list complete fail."`

## Blockers

_None._
