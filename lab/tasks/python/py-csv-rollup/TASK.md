# Extend a CSV reader with grouped totals

The existing `rows FILE` command returns an array of objects containing each CSV row as strings.
Preserve that behavior. Add `rollup FILE GROUP VALUE`, using the named header columns to group
exact strings and sum signed base-10 integer values. Python `int` whitespace and sign handling
is accepted; decimals and blank numeric cells are invalid. CSV files are UTF-8 and use standard
CSV quoting, including commas and newlines inside fields. Headers are unique; all rows have
the header's width. Empty string group names are valid.

Return `[{"group":name,"count":row_count,"sum":integer_total},...]` sorted by group string.
Header-only files produce `[]`. Missing requested headers return `unknown column`; any invalid
numeric cell returns `invalid integer`, with no partial result. Invalid CLI shapes return
`usage: rows FILE | rollup FILE GROUP VALUE`. No floating-point or monetary rounding is needed.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
