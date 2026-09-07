# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Repair durable_queue package and JSON CLI to satisfy CONTRACT.md with regression tests."`

## Assumptions

- `"Python 3.12 stdlib only, no network, daemon, or external packages."`
- `"Strict validation: bool is not int, finite JSON only, now integer \u003e=0."`
- `"Each CLI invocation is a fresh process on the same SQLite file."`
- `"Test databases use temporary directories."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Core validation and atomic submit"`
- Instructions: `"Add strict validation and atomic submit: no input mutation, sorted-unique deps, batch dup/unknown/self/cycle rejection, idempotent only on normalized original-spec match, rollback with no recovery side-effect, detached 10-key views."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"V1"`
- `"V3"`

**Verification**

- `"CHK1"`
- `"CHK3"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Atomic leases and transitions"`
- Instructions: `"Implement atomic leases with BEGIN IMMEDIATE and WAL: claim recovers expired then picks pending ready eligible by priority then lex-min ID; recover/completion enforce owner, attempt, lease, terminal, and retry-delay rules."`

**Affected files**

- `"durable_queue/queue.py"`
- `"durable_queue/storage.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"V1"`
- `"V2"`
- `"V3"`

**Verification**

- `"CHK1"`
- `"CHK2"`
- `"CHK3"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"CLI contract"`
- Instructions: `"Harden CLI: UTF-8 object request, exact op and kwargs, reject unknown fields, single sorted-keys JSON plus newline exit 0, any ValueError/IO/usage/DB failure exit 2 with empty stdout."`

**Affected files**

- `"durable_queue/__main__.py"`

**Dependencies**

- `"S2"`

**Acceptance criteria**

- `"V1"`
- `"V3"`

**Verification**

- `"CHK1"`
- `"CHK2"`
- `"CHK3"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Regression tests"`
- Instructions: `"Add tests/test_regression.py covering rollback, idempotent/conflict, ordering, expiry/retry-limit, stale-owner rejection, failed-dep ineligibility, plus multiprocessing and subprocess CLI durability and exclusivity."`

**Affected files**

- `"tests/test_regression.py"`

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"V1"`
- `"V2"`
- `"V3"`

**Verification**

- `"CHK1"`
- `"CHK2"`

## Risks

- `"Cross-process claim race without atomic transaction."`
- `"Bool versus int and NaN/Infinity validation gaps."`
- `"Original-spec idempotency versus mutated state confusion."`
- `"CLI stdout pollution on error paths."`

## Acceptance criteria

- `"V1"`: `"Starter plus new regression tests pass under python3.12 unittest discover."`
- `"V2"`: `"Separate-process reopen persists commits and concurrent claimants never share an active lease."`
- `"V3"`: `"Submit, view, claim, recover, complete, fail and CLI success/error behavior match public contract."`

## Verification strategy

- `"CHK1"`: `"Run python3.12 -m unittest discover -s tests -v; require all pass."`
- `"CHK2"`: `"Run CLI matrix with python3.12 -m durable_queue --db $TMP/db.sqlite --request $TMP/req.json for all ops; assert exit 0 JSON and error cases exit 2 empty stdout."`
- `"CHK3"`: `"Run contract audit via python3.12 -c \"import durable_queue; help(durable_queue.Queue)\" plus manual view-sort, atomic-batch, and terminal-state checks."`

## Discoveries

- `"queue.py submit is unvalidated INSERT OR REPLACE without atomicity or cycle checks."`
- `"claim, recover, complete, fail are NotImplemented."`
- `"storage.py lacks WAL and BEGIN IMMEDIATE transaction."`
- `"__main__.py lacks op/kwarg validation and exit-2 empty-stdout handling."`
- `"tests/test_public.py has only 3 happy-path tests."`

## Blockers

_None._
