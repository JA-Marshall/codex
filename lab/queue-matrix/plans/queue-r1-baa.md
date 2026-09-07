# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue submit/views, atomic claim/recover, stale-safe complete/fail, and strict JSON CLI with separate-process regression tests."`

## Assumptions

- `"Python 3.12 stdlib and sqlite only; test DBs in temp dirs, no network/daemon/packages."`
- `"Central strict validators: now int\u003e=0, lease_seconds positive int, retry_delay int\u003e=0, bool is never int."`
- `"Cross-process safety via SQLite file with WAL and BEGIN IMMEDIATE; no wall clock."`
- `"Preserve Queue(db_path) and python -m durable_queue entry points and signatures."`

## Implementation steps

### Step `"s1-storage-tx"`

- ID: `"s1-storage-tx"`
- Title: `"Storage transactions and validators"`
- Instructions: `"Harden storage.py: WAL mode, busy timeout, BEGIN IMMEDIATE transaction helper, strict_int excluding bool, finite-JSON check, normalized-spec plus mutable-state schema with migration preserving existing jobs."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"ac-submit"`
- `"ac-views"`
- `"ac-claim"`
- `"ac-recover"`
- `"ac-transitions"`

**Verification**

- `"v1"`
- `"v2"`

### Step `"s2-submit-views"`

- ID: `"s2-submit-views"`
- Title: `"Atomic submit and views"`
- Instructions: `"Implement submit/get/list: no input mutation, strict field whitelist/defaults, dup/unknown/self/cycle check incl. DB deps, atomic single-TX batch, idempotent same-spec no-op, exact 12-key detached sorted views."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"s1-storage-tx"`

**Acceptance criteria**

- `"ac-submit"`
- `"ac-views"`

**Verification**

- `"v1"`

### Step `"s3-claim-recover"`

- ID: `"s3-claim-recover"`
- Title: `"Atomic claim and lease recovery"`
- Instructions: `"Implement claim/worker-now-lease validation plus recover(now): in one BEGIN IMMEDIATE TX recover lease_until\u003c=now with ready_at rules, then claim one eligible pending job by priority then ID with attempts+1 and lease_until=now+lease_seconds."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"s2-submit-views"`

**Acceptance criteria**

- `"ac-claim"`
- `"ac-recover"`

**Verification**

- `"v1"`
- `"v2"`

### Step `"s4-finish-cli-tests"`

- ID: `"s4-finish-cli-tests"`
- Title: `"Transitions, CLI, and regression tests"`
- Instructions: `"Implement complete/fail stale-safe transitions with bounded retries and terminal guards, rewrite CLI with strict op/field whitelist and exit-2 empty-stdout handling, add tests/test_regress.py with subprocess exclusivity and durability tests."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/__main__.py"`
- `"tests/test_regress.py"`

**Dependencies**

- `"s3-claim-recover"`

**Acceptance criteria**

- `"ac-transitions"`
- `"ac-cli"`
- `"ac-regress"`

**Verification**

- `"v1"`
- `"v2"`
- `"v3"`

## Risks

- `"Cross-process double-claim under concurrency; mitigated by single BEGIN IMMEDIATE TX with conditional UPDATE plus re-read."`
- `"Invalid batch partially mutating or triggering recovery; mitigated by full validation before TX and single-TX rollback."`
- `"Stale/wrong-owner/expired complete/fail writing or recovering; mitigated by read-check-write in same TX with attempt and now\u003clease_until checks."`
- `"Cycle and idempotent-resubmit confusion with existing jobs; mitigated by normalized-spec store plus graph check over batch plus DB."`

## Acceptance criteria

- `"ac-submit"`: `"Atomic submit: full pre-TX validation, dup/unknown/self/unknown-dep/cycle reject whole batch with no writes and no recovery side-effects; idempotent same normalized spec is no-op."`
- `"ac-views"`: `"Views: exact 12-key detached copies, sorted unique deps, list sorted by ID, get/list validate IDs and never implicitly recover."`
- `"ac-claim"`: `"Claim: recovers expired first in same TX, picks pending ready eligible highest priority then smallest ID, attempts+1 with lease, cross-process exclusivity."`
- `"ac-recover"`: `"Recover: lease_until\u003c=now only, attempts\u003cmax-\u003epending ready_at=expired lease else failed unchanged ready_at, clears owner, no attempt bump, idempotent."`
- `"ac-transitions"`: `"Complete/fail: require running+owner+attempt equality+now\u003clease_until, validate retry_delay, bounded retries, terminals immutable, stale never writes/recovers."`
- `"ac-cli"`: `"CLI keeps Queue and python -m durable_queue, strict op/field whitelist, sorted-keys single JSON plus newline exit 0, all error paths exit 2 empty stdout."`
- `"ac-regress"`: `"Focused regress tests incl. real separate-process claim exclusivity and kill/restart durability, all local temp DBs."`

## Verification strategy

- `"v1"`: `"Run python3.12 -m unittest discover -s tests -v covering validation, atomicity, ordering, retries, terminals, and detached views."`
- `"v2"`: `"Run python3.12 -m unittest tests.test_regress -v: two processes claim same job get distinct owners; committed jobs survive close/reopen."`
- `"v3"`: `"Run CLI matrix via python3.12 -m durable_queue --db TMP --request FILE for success shape and exit-2 paths: bad op/fields/UTF8/missing/unavailable DB."`

## Discoveries

- `"storage.connect single jobs(id,data JSON) table, timeout 5, no WAL or BEGIN IMMEDIATE; races and torn reads likely."`
- `"queue.submit INSERT OR REPLACE with no validation, atomicity, idempotency, cycle or unknown-field checks; overwrites state."`
- `"claim/recover/complete/fail unimplemented; get/list lack ID validation and detached-copy guarantees."`
- `"__main__ mutates request, allows unknown ops/fields, no exit-2 handling for bad JSON/UTF8/missing file/unavailable DB."`

## Blockers

_None._
