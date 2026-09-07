# Extend a manifest viewer into a copy planner

Preserve `rust-copy-plan list`, which reads a source manifest on stdin and reprints it sorted by path. Add `rust-copy-plan diff TARGET [--keep-extra]`; TARGET is a UTF-8 manifest file, resolved from the process working directory. This command plans changes only and must not alter files.

Manifest records are exactly `relative/path<TAB>u64-size<TAB>nonempty-digest`; empty physical lines are skipped. Fields are not trimmed. Paths must have nonempty slash-separated components other than `.` or `..`, and contain neither backslash nor colon. Duplicate paths are invalid, even if records match. Digests are opaque case-sensitive strings.

For the union of source and target paths in Rust string order, print `COPY<TAB>path<TAB>source-size` if absent from target or if either size or digest differs. Print `DELETE<TAB>path` for target-only paths unless `--keep-extra` is set. Unchanged paths print nothing. End with `TOTAL<TAB>copy-count<TAB>delete-count<TAB>sum-of-copy-bytes` and a newline, including empty plans. Use checked u64 addition for the byte sum.

Success exits 0. Invalid input, duplicate paths, unreadable targets, byte overflow, or incorrect arguments exit 2 with empty stdout and `error:` stderr. Input row errors contain `line N`; target errors also contain `target`; overflow contains `overflow`; command errors contain `usage`. Validate both full manifests before producing a plan. Do not inspect the actual files named in manifests, interpret digests, recurse directories, or perform copies/deletions.

Work only in `src/` and `tests/`. Keep the CLI contract and existing public behavior. Use Rust 1.95 and the standard library; do not add dependencies or modify Cargo metadata. The project is deliberately detached from the parent workspace. Run `just test` in the project (with an isolated `CARGO_TARGET_DIR`) to execute its public tests. No network, services, clock, or environment configuration is needed. Input sizes are modest; do not add unrelated features.
