# Build a deterministic dependency planner

Complete `rust-build-order` (no arguments), which reads a small dependency manifest on stdin and prints a build order. `parser.rs` already recognizes the format; implement the planner and integrate it with the scaffold.

Records are `name: dependency, dependency`; whitespace surrounding names is ignored. Empty lines and trimmed lines beginning with `#` are ignored. Names contain one or more ASCII letters, digits, `_`, or `-`. A declaration with no dependencies is legal. Dependencies are nodes even if never separately declared. Repeated declarations union their dependency sets; duplicate edges count once.

Emit every node exactly once with dependencies first. At each individual selection, choose the lexicographically smallest currently ready node (Rust string order); newly ready nodes compete immediately with previously ready nodes. Print one node per newline; empty input prints nothing. Cycles, including self-dependencies and cycles in otherwise disconnected graphs, must produce exit 2, empty stdout, and stderr containing `cycle`. Invalid records produce exit 2 and `line N` diagnostics using physical input line numbers. Arguments are rejected with a usage error. Success exits 0. Do not add graph visualization, parallel execution, or external packages.

Work only in `src/` and `tests/`. Keep the CLI contract and existing public behavior. Use Rust 1.95 and the standard library; do not add dependencies or modify Cargo metadata. The project is deliberately detached from the parent workspace. Run `just test` in the project (with an isolated `CARGO_TARGET_DIR`) to execute its public tests. No network, services, clock, or environment configuration is needed. Input sizes are modest; do not add unrelated features.
