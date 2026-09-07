# Repair release-candidate ordering

The release-list CLI sometimes places release candidate 10 before release candidate 2.
Repair version precedence while preserving the interface: no arguments; stdin is a JSON array
of version strings; output is the original strings in ascending precedence, stable for ties.

Accepted syntax is MAJOR.MINOR.PATCH with optional `-PRERELEASE` and `+BUILD`. Core numbers are
nonnegative ASCII integers with no leading zeros except `0`. Prerelease/build are nonempty
dot-separated identifiers using ASCII letters, digits, and hyphens. Numeric prerelease
identifiers cannot have leading zeros; numeric build identifiers can. Reject an invalid member
with `invalid version`, and non-array inputs with `invalid version list`.

Compare core numbers numerically. A prerelease precedes the corresponding release. Compare its
dot identifiers left to right: numeric numerically, numeric before nonnumeric, nonnumeric by
ASCII string order. If a shared prefix ties, fewer identifiers precede more. Build metadata has
no effect, so equal-precedence strings retain their input order. Do not normalize output strings.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
