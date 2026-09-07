# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue package and JSON CLI per CONTRACT.md with atomic durability and regression tests, approval-gated with no implementation."`

## Assumptions

- `"Python 3.12 stdlib only with sqlite3, json, argparse and unittest plus subprocess."`
- `"Now is sole integer clock; bool is never valid int; schema may change but Queue(db_path) and python -m durable_queue preserved."`
- `"Tests use temp dirs only; no network, packages, daemon or UI."`

## Implementation steps

### Step `"s-storage"`

- ID: `"s-storage"`
- Title: `"Storage and validation core"`
- Instructions: `"Harden storage: WAL, busy_timeout, BEGIN IMMEDIATE transactions, normalized orig-spec plus runtime state; add strict validators for ids, worker, plain ints, finite JSON, sorted-unique deps and exact view keys without mutating input."`

**Affected files**

- `"durable_queue/storage.py"`
- `"durable_queue/queue.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"ac-submit"`

**Verification**

- `"v-unittest"`
- `"v-api-matrix"`

### Step `"s-submit"`

- ID: `"s-submit"`
- Title: `"Atomic submit"`
- Instructions: `"Implement atomic submit: batch duplicate, unknown, self and cycle checks including existing jobs; idempotent same normalized orig-spec no-op else conflict; whole-batch rollback with no recovery side effects."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"s-storage"`

**Acceptance criteria**

- `"ac-submit"`

**Verification**

- `"v-unittest"`
- `"v-api-matrix"`

### Step `"s-transitions"`

- ID: `"s-transitions"`
- Title: `"Claim, recover and completion transitions"`
- Instructions: `"Implement claim with recovery then priority-desc id-asc eligible pick and attempts increment; recover reset with ready_at rules; complete and fail with running plus owner plus attempt plus lease checks, retry_delay cap and terminal guards."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"s-storage"`
- `"s-submit"`

**Acceptance criteria**

- `"ac-transitions"`

**Verification**

- `"v-unittest"`
- `"v-api-matrix"`

### Step `"s-cli-tests"`

- ID: `"s-cli-tests"`
- Title: `"CLI and regression tests"`
- Instructions: `"Harden CLI allowlist, UTF-8 and JSON handling, exit-2 empty-stdout and sorted-keys newline output; add tests/test_regression.py for validation, rollback, idempotency, ordering, leases, bounded retry, subprocess claim exclusivity and CLI durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"s-submit"`
- `"s-transitions"`

**Acceptance criteria**

- `"ac-cli"`
- `"ac-tests"`

**Verification**

- `"v-unittest"`
- `"v-cli-matrix"`

## Risks

- `"Cross-process double-claim without BEGIN IMMEDIATE plus single predicated UPDATE."`
- `"Bool-as-int, NaN and Infinity, finite-JSON and int-range validation slips."`
- `"Partial batch write on ValueError without full rollback and no implicit recovery on error."`
- `"CLI leaking stdout on error or non-deterministic key order."`

## Acceptance criteria

- `"ac-submit"`: `"Submit validates, normalizes, enforces atomic idempotent batch with rollback on any invalid input."`
- `"ac-transitions"`: `"Claim, recover, complete and fail enforce validation, atomic ownership, retry bounds and stale-reject with no write on error."`
- `"ac-cli"`: `"CLI enforces strict op and field allowlist, sorted-keys newline JSON on success and exit 2 with empty stdout on failure."`
- `"ac-tests"`: `"Regression tests cover validation, rollback, ordering, leases and separate-process exclusivity and durability."`

## Verification strategy

- `"v-unittest"`: `"Run python3.12 -m unittest discover -s tests -v covering starter plus new subprocess exclusivity and durability tests."`
- `"v-api-matrix"`: `"Run python3.12 API matrix script checking submit, cycles, idempotency, claim order and deps, recover, fail retry and terminal plus stale and owner rejects with DB-unchanged checks."`
- `"v-cli-matrix"`: `"Run python3.12 CLI matrix via python3.12 -m durable_queue --db PATH --request FILE checking success JSON and exit-2 cases for bad JSON, UTF-8, op, fields and missing DB."`

## Discoveries

- `"queue.py submit uses INSERT OR REPLACE without validation, atomicity, cycles or idempotency; claim, recover, complete and fail raise NotImplementedError."`
- `"storage.py single jobs(id,data) blob table without WAL, busy_timeout or explicit BEGIN IMMEDIATE control."`
- `"__main__.py lacks op and field validation, exit-2 with empty stdout, and sorted-keys newline guarantee."`
- `"tests/test_public.py has 3 smoke tests only; __init__.py preserves Queue entry point."`

## Blockers

_None._
