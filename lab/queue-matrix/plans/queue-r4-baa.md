# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md and wait for human approval before implementation."`

## Assumptions

- `"Python 3.12 stdlib plus sqlite only, integer now semantics."`
- `"Each CLI invocation is a fresh process sharing one SQLite file."`
- `"Test databases live in temporary directories."`
- `"Preserve Queue and python -m durable_queue entry points."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Storage and transaction foundation"`
- Instructions: `"Harden storage: enable WAL, set busy timeout, extend schema for state columns plus original spec, add BEGIN IMMEDIATE transaction helper; Queue init preserves existing jobs."`

**Affected files**

- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic submit and detached views"`
- Instructions: `"Implement submit/get/list: strict field and type checks without caller mutation, sorted-unique deps, duplicate plus unknown plus self plus cycle rejection, spec-match idempotency, single-transaction rollback, detached views sorted by ID."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"A1"`

**Verification**

- `"V1"`
- `"V3"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Claim, recovery, and completion transitions"`
- Instructions: `"Implement claim with implicit recovery only, priority then ID ordering, pending plus ready plus attempts plus succeeded-deps eligibility, single-row atomic claim; implement recover, complete, and fail with attempt bounds, lease clearing, and stale plus expired plus owner plus terminal rejection."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"A2"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Strict CLI and regression tests"`
- Instructions: `"Harden CLI to strict op and field allowlist, exit 0 with sorted-keys JSON plus newline and exit 2 with empty stdout on any failure; add focused regressions for invalid batches, stale/expired paths, retries, ordering, CLI exit codes, and separate-process exclusivity and durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"A3"`
- `"A4"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Cross-process double-claim without BEGIN IMMEDIATE plus atomic conditional update."`
- `"Invalid batch must leave zero writes and trigger no implicit recovery."`
- `"Stale attempt, wrong worker, expired lease, and terminal states need read-checked pre-write rejection."`
- `"Strict bool-is-not-int, finite JSON, cycle and unknown and self-dependency, and ready_at reset semantics."`

## Acceptance criteria

- `"A1"`: `"Submit is atomic, strictly validated, idempotent on normalized spec match, returns detached sorted views; get/list sorted, validated, no implicit recovery."`
- `"A2"`: `"Claim atomically recovers expired leases then claims one eligible job by priority/ID with dependency-succeeded check; recover/complete/fail enforce attempt bounds, lease expiry, owner/attempt match with no spurious writes."`
- `"A3"`: `"CLI validates op and fields, success prints one sorted-keys JSON plus newline exit 0, all failures exit 2 empty stdout; committed work survives restarts, temp-dir DBs, stdlib only."`
- `"A4"`: `"Full contract matrix passes via python3.12 -m unittest discover -s tests -v including separate-process exclusivity and durability regressions."`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v for full contract matrix beyond starter tests."`
- `"V2"`: `"Run separate-process claim-exclusivity and kill-restart durability checks via subprocess CLI and API against temp-dir DBs."`
- `"V3"`: `"Run targeted invalid-batch rollback, stale and expired rejection, retry and ordering, and CLI exit-2 checks via python3.12 -m unittest and CLI exit-code probes."`

## Discoveries

- `"submit skips validation, mutates via INSERT OR REPLACE, breaks atomicity and idempotency."`
- `"claim/recover/complete/fail are NotImplemented; no scheduling or lease logic exists."`
- `"storage.connect uses single jobs(id,data) table, no WAL, timeout tuning, or transaction helper."`
- `"__main__ pops op without validation, leaks exceptions, misses exit-2 and sorted-keys contract."`
- `"Starter tests cover only empty, reopen, and happy-path claim."`

## Blockers

_None._
