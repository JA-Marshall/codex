# Build a persistent document index

Implement `build ROOT INDEX` and `query INDEX TEXT...`. Build recursively visits regular files
under ROOT with the case-sensitive suffix `.txt`, excluding INDEX itself if it is inside ROOT.
No symlinks or unreadable inputs are supplied. Decode UTF-8. Tokens are maximal runs of Unicode
alphanumeric characters, excluding underscores, after Unicode casefolding. Include empty
documents. Document keys are relative paths using `/`, never absolute paths.

Replace INDEX on every build, creating parent directories. Its exact UTF-8 format is JSON
`{"version":1,"documents":{"relative.txt":{"term":count}}}` with sorted keys at all levels,
no separator whitespace, literal non-ASCII characters, and one final LF. Return document and
distinct-term counts as `{"documents":N,"terms":U}`. Never merge stale data into a rebuild.

Query tokenizes the joined TEXT arguments identically and uses distinct query terms. Return
documents containing *every* query term as `[{"path":P,"score":S},...]`, where S sums the
stored frequencies of distinct query terms. Sort by descending score, then path. An empty
token set matches nothing. Build and query run in separate processes; the on-disk index is
the complete persistent state. Invalid CLI shapes return `usage: build ROOT INDEX | query INDEX TEXT`.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
