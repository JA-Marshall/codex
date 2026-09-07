# Repair duplicate-aware CSV reconciliation

Users report that removing one of several identical CSV records is not shown in the change report.
Repair `BEFORE AFTER` while preserving existing unique-row reports. Read UTF-8 CSV with standard
quoting. Both files must have nonempty, unique headers and identical sets of column names; column
order may differ. Invalid/duplicate headers return `invalid header`, wrong-width data rows return
`invalid row`, and differing header sets return `schema mismatch`. Blank lines follow Python CSV
parsing. Field strings, including empty strings and embedded newlines, are compared exactly.

Return `{"columns":[...],"removed":[{"row":{...},"count":N}],"added":[...]}`. Columns are
alphabetically sorted. A record's identity is the complete mapping of header to field, and
duplicate records contribute multiplicity. Report only the positive surplus on each side,
coalescing identical surplus rows into one entry. Sort each result array by the tuple of field
values in sorted-column order. Preserve the inputs byte-for-byte.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
