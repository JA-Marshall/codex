# Repair shrinking interval unions

`rust-ranges` (no arguments) merges half-open i64 ranges read as `start,end` lines on stdin. A customer reproduction is:

```text
0,10
2,4
8,12
```

The current implementation incorrectly shrinks an interval when a contained interval arrives and then emits two ranges. Repair the merger while preserving its parser and CLI contract.

Trim whitespace around each integer and ignore whitespace-only lines. Reject start > end. Equal endpoints denote empty ranges and disappear. Sort numerically by start then end; merge overlap and touching endpoints. Print the minimal disjoint union in increasing numeric order as `start,end` newline records. Never enumerate individual integers or subtract endpoints (i64 extremes are valid). Empty input or only empty intervals prints nothing.

Success exits 0. Malformed rows or reversed ranges exit 2, empty stdout, and stderr containing physical `line N`. Unexpected arguments exit 2 with `usage`. Preserve validation of all rows before output. Scope is the interval utility only; no new modes or dependencies.

Work only in `src/` and `tests/`. Keep the CLI contract and existing public behavior. Use Rust 1.95 and the standard library; do not add dependencies or modify Cargo metadata. The project is deliberately detached from the parent workspace. Run `just test` in the project (with an isolated `CARGO_TARGET_DIR`) to execute its public tests. No network, services, clock, or environment configuration is needed. Input sizes are modest; do not add unrelated features.
