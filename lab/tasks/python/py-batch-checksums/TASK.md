# Isolate file failures in a concurrent verifier

Maintain the existing artifact verifier: `ROOT MANIFEST REPORT`. It reads a manifest
array of exactly `{"id":unique_nonempty_string,"path":nonempty_string,"sha256":64_lowercase_hex}`
entries. Invalid manifests return `invalid manifest` before processing files or writing REPORT.
Preserve SHA-256 over exact file bytes, including UTF-8 and CRLF, success/mismatch output, input
order. Repeated paths under distinct IDs are valid. The starter uses a four-worker pool; this is
implementation context. Acceptance measures deterministic results and failure isolation, not parallel
execution or worker count.

Reliability target: one missing, non-file, or unsafe path must become a per-entry error while
all other entries still finish. Paths are portable slash-separated relative paths: reject a
leading slash, any backslash or colon, or any empty, `.` or `..` component with `unsafe path`.
Apply that check before touching the filesystem. Missing paths and directories produce
`not a file`; an OS read failure produces `unreadable file`. No symlinks are supplied.

Successful/mismatch entries remain `{"id":ID,"status":"ok"|"mismatch","actual":hex}`.
Errors are `{"id":ID,"status":"error","error":message}`. REPORT contains
`{"results":[entries_in_manifest_order],"summary":{"ok":N,"mismatch":N,"error":N}}`, as
recursively sorted-key compact JSON, literal non-ASCII UTF-8 and final LF. Return the summary
object to stdout and exit 0 even when some entries fail. Existing REPORT must be replaced on
success and unchanged for manifest validation failure. Its parent exists. Empty manifests
produce an empty report and zero counts. Never modify input files; no retries or network access.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
