# Add atomic booking rescheduling

The existing calendar supports `list STATE` and `add STATE`; commands read a booking JSON object
from stdin where needed. State is a JSON array; a missing state file means an empty calendar.
Preserve add/list semantics and add `reschedule STATE`, taking a complete replacement booking.
Bookings contain exactly `id`, `room` (nonempty strings), `start`, `end` (integers, excluding
booleans), with start < end. Times are abstract integers. IDs are globally unique. Overlap in
one room is forbidden; intervals are half-open so touching endpoints are allowed.

Reschedule must require an existing ID (`unknown id` before other booking validation), exclude
that booking from conflict checks, validate the replacement, and save only on success. A move
may change room or times, and an identical replacement succeeds. Any failure must preserve the
state file's exact bytes. Existing validation errors are `invalid booking`, `duplicate id`,
and `conflict`. Unknown commands return `unknown command`.

Successful add/reschedule returns `{"ok":true}` and writes all bookings sorted by ID, JSON with
sorted object keys, compact separators, default ASCII escapes, and final LF. List does not write;
it returns bookings sorted by `(room,start,id)`. Parent directories already exist.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
