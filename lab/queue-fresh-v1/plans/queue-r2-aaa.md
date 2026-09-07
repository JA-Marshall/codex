# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Complete durable_queue Python 3.12 stdlib package and JSON CLI per CONTRACT.md with atomic durable submission, claims, recovery, retries and regression tests."`

## Assumptions

- `"Python 3.12 stdlib only: sqlite3, json, argparse, tempfile, unittest, subprocess."`
- `"Preserve from durable_queue import Queue and python -m durable_queue entry points."`
- `"All time via explicit now int\u003e=0; test DBs in temp dirs; no network/daemon."`

## Implementation steps

### Step `"s1"`

- ID: `"s1"`
- Title: `"Storage durability and validation core"`
- Instructions: `"Harden storage.py: WAL, busy timeout, BEGIN IMMEDIATE txn helper and state+spec schema; add strict validators: bool is not int, finite JSON payload, sorted-unique normalized deps, no caller mutation."`

**Affected files**

- `"durable_queue/storage.py"`
- `"durable_queue/queue.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"ac-submit"`

**Verification**

- `"v1"`

### Step `"s2"`

- ID: `"s2"`
- Title: `"Atomic submit and views"`
- Instructions: `"Implement atomic submit/get/list: pre-validate whole batch, dup/unknown/self/cycle check, idempotent only if normalized ORIGINAL spec matches, whole-batch rollback, detached exact-10-key views sorted by ID."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"s1"`

**Acceptance criteria**

- `"ac-submit"`

**Verification**

- `"v1"`
- `"v3"`

### Step `"s3"`

- ID: `"s3"`
- Title: `"Claims and lifecycle transitions"`
- Instructions: `"Implement claim/recover/complete/fail in single txn: recover expired leases (ready_at=expired lease or failed), claim highest priority then lex-smallest ID with attempts+1, enforce running+owner+attempt+now\u003clease_until and bounded retry_delay, no write on ValueError."`

**Affected files**

- `"durable_queue/queue.py"`

**Dependencies**

- `"s2"`

**Acceptance criteria**

- `"ac-claim"`
- `"ac-lifecycle"`

**Verification**

- `"v1"`
- `"v2"`

### Step `"s4"`

- ID: `"s4"`
- Title: `"CLI contract and regression tests"`
- Instructions: `"Harden CLI to whitelisted ops with no unknown fields, sorted-keys single line exit 0, exit 2 empty stdout on any error; add tests/test_regression.py with invalid-batch rollback, lease/stale/retry bounds, subprocess claim exclusivity and reopen durability."`

**Affected files**

- `"durable_queue/__main__.py"`
- `"tests/test_regression.py"`

**Dependencies**

- `"s3"`

**Acceptance criteria**

- `"ac-cli"`

**Verification**

- `"v1"`
- `"v2"`
- `"v3"`

## Risks

- `"Lost-update/duplicate lease without BEGIN IMMEDIATE plus WAL and busy timeout."`
- `"True==1 and NaN/Infinity leaking through int/JSON validation."`
- `"Implicit recover on failed validation or stdout pollution on CLI error."`

## Acceptance criteria

- `"ac-submit"`: `"Atomic validated submit, idempotent on normalized original spec only, exact 10-key detached views, list sorted by ID."`
- `"ac-claim"`: `"Atomic claim with implicit recover, priority then lex-ID order, cross-process exclusivity, dep gating, failed dep stays ineligible."`
- `"ac-lifecycle"`: `"Recover/complete/fail enforce lease/owner/attempt bounds, retry_delay and terminal states; ValueError writes nothing including no recover."`
- `"ac-cli"`: `"CLI whitelisted ops, sorted-keys single line exit 0; all errors exit 2 empty stdout; durability across restarts; full suite passes."`

## Verification strategy

- `"v1"`: `"Full contract suite: run python3.12 -m unittest discover -s tests -v; must pass starter plus new regression for submit/claim/deps/lease/stale/retry."`
- `"v2"`: `"Cross-process check: run python3.12 -m unittest tests.test_regression -v and concurrent python3.12 -m durable_queue claim invocations; distinct leases and reopen durability required."`
- `"v3"`: `"Atomicity and CLI check: run python3.12 -m durable_queue --db TMP --request FILE for malformed/unknown-op/bad-args cases; invalid batches leave DB unchanged, CLI exits 2 with empty stdout."`

## Discoveries

- `"storage.py: single jobs(id,data) blob table, no WAL/timeout/BEGIN IMMEDIATE; unsafe for cross-process claim."`
- `"queue.py: submit uses INSERT OR REPLACE no validation/atomicity/cycles; claim/recover/complete/fail NotImplemented; get/list no ID validation or detached-copy guarantee."`
- `"__main__.py: request.pop(op)+getattr with no whitelist, unknown-field, UTF-8/missing-file/DB error handling; risks traceback to stdout."`
- `"tests/test_public.py: only 3 starter tests; no invalid-batch rollback, lease expiry, stale attempt, retry bound, subprocess coverage."`

## Blockers

_None._
