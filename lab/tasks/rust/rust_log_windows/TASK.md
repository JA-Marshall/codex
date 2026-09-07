# Add time-window log counts

The existing `rust-log-windows count LEVEL` command counts matching log levels. Add `rust-log-windows window LEVEL START END`, preserving `count` exactly.

Read stdin records as `unsigned-u64-timestamp<TAB>nonempty-level<TAB>message`. The message can be empty or contain tabs. Empty physical lines are skipped; fields are otherwise not trimmed. Levels are case sensitive and unrestricted except that the field must be nonempty. Log records may arrive in any timestamp order. `window` counts exact level matches with timestamps in the half-open interval `[START, END)`. Both bounds must be valid u64 decimal strings with START <= END; equal bounds yield zero. Print the decimal count followed by a newline and exit 0.

Validate every record even if outside the window or at another level. Invalid records produce exit 2, empty stdout, and stderr containing the one-based physical `line N`. Bad ranges contain `range`; incorrect command shapes contain `usage`. Do not introduce sorting, timezone conversion, date parsing, or changes to the old count command.

Work only in `src/` and `tests/`. Keep the CLI contract and existing public behavior. Use Rust 1.95 and the standard library; do not add dependencies or modify Cargo metadata. The project is deliberately detached from the parent workspace. Run `just test` in the project (with an isolated `CARGO_TARGET_DIR`) to execute its public tests. No network, services, clock, or environment configuration is needed. Input sizes are modest; do not add unrelated features.
