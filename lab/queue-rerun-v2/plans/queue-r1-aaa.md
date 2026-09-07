# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md with atomic durability, leases, retries, CLI codes, and process-level regression tests."`

## Assumptions

- `"Python 3.12 stdlib-only"`
- `"Explicit now int \u003e=0, bool invalid for all contract ints"`
- `"Test DBs in temp dirs"`
- `"Preserve Queue and python -m durable_queue entry points"`
- `"No network/daemon/UI"`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Store and atomic submit"`
- Instructions: `"Storage: WAL + BEGIN IMMEDIATE helper. Submit: strict normalize/validate, batch atomicity, cycle/unknown/self check, idempotent iff normalized original spec matches, store spec blob separate from mutable view, deep-copy in/out."`

**Affected files**

- `"durable_queue/storage.py"`
- `"durable_queue/queue.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic claim and recover"`
- Instructions: `"Single txn: validate worker/now/lease_seconds, run recover semantics, then claim one eligible pending job by priority DESC id ASC, set running/attempts+1/lease; failed deps stay ineligible."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC2"`
- `"AC3"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Stale-safe complete/fail"`
- Instructions: `"Txn validate running+worker+attempt==current+now\u003clease_until else ValueError no-write/no-recover; complete-\u003esucceeded, fail-\u003epending ready_at=now+delay or failed, clear lease, cap attempts."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`
- `"S2"`

**Acceptance criteria**

- `"AC4"`

**Verification**

- `"V1"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"CLI and regression tests"`
- Instructions: `"Rewrite CLI strict op/kw whitelist, UTF-8/object checks, sorted-keys+newline exit0 else exit2 empty stdout. Add regression tests plus subprocess 2-process claim-exclusivity and reopen durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`
- `"tests/test_processes.py"`

**Dependencies**

- `"S1"`
- `"S2"`
- `"S3"`

**Acceptance criteria**

- `"AC5"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Cross-process double-claim without IMMEDIATE txn"`
- `"Invalid batch must rollback including skipped recovery"`
- `"Bool-vs-int, NaN/Inf JSON, dep cycles, stale-attempt rejection"`

## Acceptance criteria

- `"AC1"`: `"Submit validates strict types/finite JSON/sorted-unique deps/cycles, atomic batch rollback, idempotent resubmit on normalized original spec, detached views."`
- `"AC2"`: `"Claim validates args, recovers expired leases first, atomically claims highest priority then smallest ID, never double-leases across processes."`
- `"AC3"`: `"Recover clears expired leases, pending with ready_at=expired lease_until if attempts\u003cmax else failed, no attempt bump, sorted IDs."`
- `"AC4"`: `"Complete/fail require running+owner+current attempt+now\u003clease_until else ValueError no-write/no-recover; bounded retries, terminal jobs final."`
- `"AC5"`: `"CLI strict op/kw whitelist, success single sorted-keys JSON+newline exit 0, all failures exit 2 empty stdout; full suite green."`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v; must be green covering submit/claim/recover/complete/fail matrix."`
- `"V2"`: `"Run python3.12 -m unittest tests.test_processes -v; concurrent subprocess claimants never share active lease, reopen preserves commits."`
- `"V3"`: `"Run python3.12 -m durable_queue --db $TMPDB --request FILE checks; success sorted JSON newline exit 0, failures exit 2 empty stdout."`

## Discoveries

- `"queue.py submit/get/list naive INSERT OR REPLACE, claim/recover/complete/fail NotImplemented"`
- `"storage.py single jobs(id,data) blob, no WAL or BEGIN IMMEDIATE txn"`
- `"__main__.py no validation, no exit-2/empty-stdout handling"`
- `"tests/test_public.py only 3 starter tests"`

## Blockers

_None._
