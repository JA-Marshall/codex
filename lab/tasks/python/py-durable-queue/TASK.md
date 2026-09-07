# Recover a queue after interrupted log writes

Maintain the existing persistent FIFO queue's `push LOG`, `pop LOG`, and `list LOG` commands.
Push reads exactly `{"id":nonempty_string,"value":JSON}` and returns `{"ok":true}`. IDs may
never be reused, even after popping (`duplicate id`); invalid push shape returns `invalid item`.
Pop returns and removes the oldest `{"id":ID,"value":V}`, or null if empty. List returns the
pending FIFO array. Missing logs mean empty queues; read/empty pop must not create a file.

The append log consists of LF-terminated JSON events: pushes contain op=`push`, id, value;
pops contain op=`pop`, id matching the current front. Preserve completed log bytes. New events
use sorted-key compact JSON, literal non-ASCII UTF-8, and final LF. Replay must reject any
malformed completed line, wrong event fields, duplicate historical ID, or invalid pop as
`corrupt log`, leaving bytes unchanged.

Reliability target: tolerate an interrupted last append by ignoring the entire final physical
line if it lacks LF, even when it happens to be valid JSON. List and empty pop leave that tail
untouched. Before a successful mutation, discard the incomplete tail and append the new event
after the last LF. A failed push must preserve even the incomplete tail. CRLF completed lines
are accepted and kept verbatim. This repairs recovery; do not add commands or concurrent-writer
support. Input logs are UTF-8, and state must survive separate process invocations.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
