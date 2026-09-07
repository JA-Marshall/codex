# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue per CONTRACT.md with durable graphs, atomic claims, lease recovery, stale guards, bounded retries, atomic batches, strict JSON CLI and process-level regression tests"`

## Assumptions

- `"Python 3.12 stdlib only; no network/packages/daemon/UI"`
- `"No wall clock: now int\u003e=0, lease_seconds positive int, bool is not int"`
- `"Queue(db_path) file-shared across processes; schema may change; preserves rows"`
- `"Tests use tmpdirs and fresh processes for durability/exclusivity"`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage schema and atomic transaction helper"`
- Instructions: `"Replace blob table with normalized jobs(id,spec,payload,prio,deps,max_attempts,ready_at,state,attempts,worker,lease_until); enable WAL, busy timeout, transaction helper with BEGIN IMMEDIATE/COMMIT/ROLLBACK; init preserves rows."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC3"`
- `"AC6"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic submit and detached views"`
- Instructions: `"Add strict validators without mutating input; whole-batch check dup/self/unknown/cycle via topological sort; same-normalized-original-spec idempotent; single-txn insert/rollback; detached sorted get/list with exact keys."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC1"`
- `"AC2"`

**Verification**

- `"V1"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Claim, recover, complete and fail transitions"`
- Instructions: `"In one IMMEDIATE txn: claim recovers expiries then claims eligible job by prio DESC,id ASC; recover maps expired to pending/failed; complete/fail guard running+owner+attempt+now\u003clease before any write, clear lease, apply bounded retry_delay."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"AC3"`
- `"AC4"`
- `"AC5"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Strict CLI and process-level regression tests"`
- Instructions: `"Harden CLI to strict op/kwarg whitelist, sorted JSON+newline exit 0, exit 2 empty stdout on error; add regression tests for validation/rollback/stale/retry/failed-dep and separate-process durability plus contended claim exclusivity."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`
- `"tests/test_processes.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC6"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Lost-update double-claim without BEGIN IMMEDIATE single-txn claim+recover"`
- `"Stale completion if complete/fail recovers or writes before guard checks"`
- `"Partial write on invalid batch without whole-batch validate then single txn rollback"`
- `"bool-as-int and non-finite JSON bypass without strict type/finite checks"`
- `"ready_at overwrite breaking original-spec idempotency vs mutable runtime state"`

## Acceptance criteria

- `"AC1"`: `"submit validates types/unknown fields/no mutation/finite JSON/sorted-unique deps; rejects dup/self/unknown/cycle atomically with rollback; existing ID is no-op only on identical normalized original spec"`
- `"AC2"`: `"get/list return detached exact-key views sorted by ID with sorted deps; validate IDs; no implicit recovery"`
- `"AC3"`: `"claim validates worker/now/lease, recovers expiries first, atomically claims one eligible pending job by prio DESC,id ASC with attempts\u003cmax and succeeded deps; single active lease across processes"`
- `"AC4"`: `"recover(now) returns sorted IDs of lease_until\u003c=now running jobs; pending+ready_at=expired lease_until or failed; clears owner/lease; no attempt bump; idempotent"`
- `"AC5"`: `"complete/fail require running+owner+attempt+now\u003clease and valid retry_delay; clear lease; succeeded or pending with ready_at=now+delay vs failed; reject stale/expired/wrong-owner/terminal without write or recovery"`
- `"AC6"`: `"CLI strict op/kwarg whitelist, one sorted JSON+newline exit 0, exit 2 empty stdout on any error, fresh-process durability; python3.12 -m unittest discover -s tests -v passes incl. new process tests"`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v covering full contract matrix: submit/get/list/claim/recover/complete/fail, validation, rollback, retries, stale guards."`
- `"V2"`: `"Run python3.12 -m unittest tests.test_processes -v and python3.12 -m unittest discover -s tests -v for multiprocessing/subprocess contended-claim exclusivity and kill-restart reopen durability."`
- `"V3"`: `"Run fresh python3.12 -m durable_queue --db PATH --request FILE per op to check sorted JSON+newline, exit 0 vs exit 2 with empty stdout, unknown-field rejection and durability."`

## Discoveries

- `"submit uses INSERT OR REPLACE blob with no validation/atomicity/idempotency/cycle checks and clobbers state"`
- `"claim/recover/complete/fail are NotImplemented; no priority/dep/lease logic"`
- `"storage.connect has no WAL/timeout/BEGIN IMMEDIATE discipline; no txn helper"`
- `"__main__ lacks strict validation, exit-2 empty-stdout, sorted-keys newline, unknown-field handling"`

## Blockers

_None._
