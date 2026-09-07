# Migrate snapshot storage without changing reads

Maintain the existing snapshot CLI while replacing its legacy serialized format. `read FILE`
returns the effective key/value object. Legacy files are arrays of `{"key":string,"value":JSON}`
records, allowing empty keys and duplicate keys; the last record wins. Preserve every JSON value
exactly, including null, false, zero, empty strings, arrays, and objects.

The measurable maintenance target: `compact FILE` must migrate legacy files to exactly
`{"version":2,"values":{...}}`, with UTF-8 literal non-ASCII, recursively sorted keys, compact
separators, and one final LF. Return `{"keys":N}`. Both read and compact must accept this v2
format. Compacting twice must produce identical bytes. Read must never write. An invalid legacy
record, unsupported version, or malformed container returns `invalid snapshot` and must leave
the file untouched. V2 requires exactly version (integer 2, not boolean) and values (object).
Inputs are syntactically valid JSON. This is a storage maintenance task; add no new commands.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
