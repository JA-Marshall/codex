# Durable queue v1

Python 3.12 standard library only. Public API: `from durable_queue import Queue`;
`Queue(db_path)` creates/opens a SQLite file, preserves existing jobs, and may be
used by independent processes. Schema/internal design may change. No daemon/network.
There is no wall clock: every timed operation receives `now`, an integer >= 0.
Booleans are not integers for any contract field. Invalid requests raise ValueError
and must leave database contents unchanged, including expiry recovery.

## Submission and views

`submit(jobs)` accepts a list (empty allowed) of job dictionaries and returns their
current views in input order. Allowed fields: `id` (required nonempty string),
`payload` (default {}, JSON object, finite JSON values only), `priority` (default 0,
signed integer), `dependencies` (default [], list of nonempty IDs, normalized to
sorted unique IDs), `max_attempts` (default 3, integer 1..100), `ready_at` (default 0,
integer >=0). Unknown fields/types are invalid. Do not mutate caller input.

Duplicate IDs within one batch are invalid. Dependencies may refer to existing
jobs or any job in this batch; unknown/self dependencies and cycles are invalid.
Submission is atomic: one invalid job rejects the whole batch. Submitting an
existing ID is an idempotent no-op only if its normalized ORIGINAL submission
specification matches, even after state/ready_at changes; conflicts reject the batch.

Every job view has EXACTLY these keys: id, payload, priority, dependencies,
max_attempts, ready_at, state, attempts, worker, lease_until. Initial state is
`pending`, attempts=0, worker=null and lease_until=null. All views are detached
copies, payload/dependencies retain JSON types, and dependencies are sorted unique.
`get(id)` returns a view or null; `list()` returns all views sorted by ID.
Both validate string IDs where applicable; they do not recover leases implicitly.

## Claims and transitions

`claim(worker, now, lease_seconds)` validates nonempty worker and positive integer
lease_seconds, recovers every expired running job, then atomically claims at most
one eligible job and returns its view (null if none). Eligibility: pending,
ready_at <= now, attempts < max_attempts, every dependency succeeded. Choose highest
priority first, then lexicographically smallest ID (Python string order). Claim
sets state=running, attempts+=1, worker=worker, lease_until=now+lease_seconds.
Two separate processes must never receive the same active lease. A job whose
dependency failed stays pending/ineligible; do not propagate failure automatically.

`recover(now)` processes running jobs with lease_until <= now and returns their
IDs sorted. Clear worker/lease_until. If attempts < max_attempts, set state=pending
and ready_at to the EXPIRED lease_until; otherwise state=failed and leave ready_at
unchanged. Recovery does not increment attempts; repeated recovery is a no-op.

`complete(id, worker, attempt, now)` and
`fail(id, worker, attempt, now, retry_delay=0)` require an existing running job,
matching worker and current attempt (positive integer), and now < lease_until.
Unknown jobs, expired/stale/wrong-owner leases and invalid arguments raise ValueError
without writing/recovering anything. Both return the resulting view, clearing
worker/lease_until. Complete sets succeeded and leaves ready_at unchanged. Fail
sets pending and ready_at=now+retry_delay if attempts < max_attempts; otherwise
sets failed and leaves ready_at unchanged. retry_delay is an integer >=0.
An older attempt must be rejected even when the same worker reclaimed the job.
Terminal jobs cannot be completed/failed/claimed again. Attempts never exceed limit.

## CLI

`python3.12 -m durable_queue --db PATH --request FILE` reads one UTF-8 JSON object.
`op` must be one of submit/get/list/claim/recover/complete/fail, with keyword fields
matching the method signature above (`jobs`, `id`, `worker`, `attempt`, `now`,
`lease_seconds`, `retry_delay`). No unknown fields. Success writes exactly one JSON
value with sorted object keys followed by one newline, exit 0. API ValueError,
malformed/non-object request, invalid UTF-8, missing file, invalid usage, unknown
operation or unavailable database must exit 2 with empty stdout; stderr is optional.
Each invocation is a fresh process using the same database; prior committed work
must survive failures/restarts. Test databases belong in temporary directories.
