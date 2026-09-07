# Build an inventory rollup CLI

Implement the missing aggregation behind `rust-inventory-rollup` (no arguments). The scaffold already parses stdin into `(name, quantity)` records; `aggregate` is intentionally unfinished.

Each nonblank, noncomment line contains exactly `name<TAB>signed i64 quantity`. Leading/trailing whitespace around each field is trimmed. A comment has `#` as its first nonwhitespace character. Names are case sensitive and may contain internal spaces. Sum quantities by trimmed name in input order, using checked i64 addition, and print one `name<TAB>total` line per distinct name in Rust string order. Keep zero and negative totals. Empty/comment-only input prints nothing. Every output record ends with a newline.

Reject command arguments, malformed records, invalid numbers, or an intermediate sum outside i64 with exit 2, stderr beginning `error:`, and empty stdout. Overflow diagnostics must contain `overflow`; malformed row diagnostics identify its one-based physical line. Success exits 0. Parse and validate the entire input before emitting output. Do not support CSV quoting or alternate delimiters.

Work only in `src/` and `tests/`. Keep the CLI contract and existing public behavior. Use Rust 1.95 and the standard library; do not add dependencies or modify Cargo metadata. The project is deliberately detached from the parent workspace. Run `just test` in the project (with an isolated `CARGO_TARGET_DIR`) to execute its public tests. No network, services, clock, or environment configuration is needed. Input sizes are modest; do not add unrelated features.
