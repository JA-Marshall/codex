# Codex laboratory foundation — plan v1 for human approval

Status: **approved by the user's explicit “Yes”; foundation implemented**. The original reviewed JSON is retained unchanged; see [`APPROVAL.json`](APPROVAL.json) for the decision and [`PROGRESS.md`](PROGRESS.md) for current validation status.

Canonical source: [`implementation-plan.json`](implementation-plan.json), plan ID `codex-lab-foundation`, revision `1`. This Markdown file is a human review companion, not the source of plan authority. Detailed source map, decisions, critique and future integration contracts: [`ARCHITECTURE.md`](ARCHITECTURE.md). Resumption state: [`PROGRESS.md`](PROGRESS.md).

Baseline: upstream `openai/codex` at `112be0bd74ce327788613f4f8f92e8b7c92447c7`, checked out in `C:/Users/james/Desktop/Code/trees/codex-lab`. The original workspace was not a Codex repository.

## Proposed scope

Build a core-independent Rust crate, `codex-rs/lab` / `codex-lab`, with:

1. Validated canonical plan revisions and stable step IDs, with progress separate from approved content.
2. Pure Markdown and JSON renderers of the same canonical revision.
3. Strict runtime workflow configuration with small, explicit inheritance and renderer-only variants.
4. Explicit content-pinned planner, executor and verifier instruction selection, one initial variant per role.
5. A state machine requiring an explicit host human decision bound to the exact run, plan revision and configuration before domain execution admission.
6. Local lab artifacts and a checked, synchronized journal of plan revisions, human edits/decisions and workflow transitions.
7. Behavioral tests and an offline inspection example that makes the approval boundary reviewable without calling a model.

This is a foundation milestone. It will **not yet enforce a gate over live Codex tool execution**, and ordinary Codex behavior will be unchanged. Live integration is a separately reviewed next milestone because existing observer/hooks APIs do not implement the necessary hard gate.

## Why this is the smallest clean boundary

- Current Codex already has `ext/extension-api`, custom providers, profile-v2, typed skill invocation, app-server clients and a detailed `rollout-trace` crate. Reuse them during integration.
- `ToolLifecycleContributor::on_tool_start` observes but cannot veto. `ApprovalReviewContributor` only sees actions chosen for approval. PreToolUse command hooks can fail open and are optional for some tools.
- Client-side scheduling can withhold an implementing turn, but read-only research turns can still reach non-filesystem side effects. A hard gate must cover actual dispatch, including nested code-mode calls and later subagents.
- A standalone state machine must not be advertised as that live gate. Building and testing its contract first avoids committing to a flawed hook workaround.

## Implementation sequence

Each step is a separate reviewable change; keep modules private and small. Stop if a listed boundary requires expanding scope.

| Stable ID | Change | Concrete files / verification |
| --- | --- | --- |
| F01 | Crate, canonical plans, validation and rendering | New `codex-rs/lab/{Cargo.toml,BUILD.bazel,src/lib.rs,src/plan.rs,src/render.rs}` plus behavioral tests. Validate dependency DAGs, stable IDs, paths and content bounds; verify JSON round-trip and both renderer outputs. |
| F02 | Workflow config and deterministic role selection | New `src/config.rs`, `src/instructions.rs`, tests, `lab/workflows/`, `lab/instructions/`. Reject cycles/unknowns/missing resources/hash changes. Assert effective Markdown/JSON workflows differ only by renderer. |
| F03 | Approval state machine | New `src/workflow.rs` and tests. Prove with a fake execution boundary that unapproved/stale actions do not run, edits and amendments revoke authority, and verification precedes completion. |
| F04 | Lab recording | New `src/run.rs` and tests. Persist canonical revisions, views, frozen instructions and decisions. Refuse collisions; inject I/O failures and verify no authority is released. Reference existing traces instead of duplicating them. |
| F05 | Offline walkthrough and contracts | New `examples/inspect.rs`, `lab/README.md`; update architecture/ledger. Show both renderer configurations without a model call or task-tool execution. Document conditional Muse setup and remaining live-gate obligations. |
| F06 | Verification and handoff | Use the pinned toolchain and repo test/build helpers; record exact outcomes and final changed-file review. Stop before live agent wiring. |

F02 and F03 depend on F01 and can be developed independently. F04 joins them; F05 and F06 complete the foundation. This sequence is a scoped implementation roadmap, not approval to add deferred integrations.

## State and plan invariants

The states are `researching`, `planning`, `awaiting_plan_approval`, `implementing`, `awaiting_plan_amendment`, `verifying`, `completed`, and `failed`.

Plan submission is distinct from approval. Only an explicit host human decision for `(run ID, plan ID, revision, canonical content digest, effective run-spec digest)` permits implementation admission. Model text, events, filesystem edits and a completed checklist cannot grant authority. The real trusted-human transport remains an integration obligation.

An amendment revokes future admissions and produces a new revision requiring review. Progress alone does not mutate the approved specification. In the live milestone, revocation must also stop/drain already-admitted work through upstream facilities before claiming the run is paused.

The canonical plan schema includes goal, assumptions, ordered steps, affected relative files, dependency IDs, risks, acceptance criteria, verification strategy, discoveries and blockers. Progress and verification evidence refer to stable IDs. Renderers cannot mutate canonical content. JSON remains persisted even when the selected view is `PLAN.md`.

Human edits to structured canonical data create revisions. Arbitrary Markdown-to-plan parsing is deferred. Future GitHub publishing belongs in a synchronization adapter; GitHub Actions orchestration is not a serializer.

## Configuration and reproducibility

The lab TOML uses a shared `plan-base` parent and named `plan-md-v1` / `plan-json-v1` children. Their only behavioral difference is `plan.renderer`. One-parent inheritance is enough initially; reject cycles, excessive depth and unknown keys. Model/provider settings stay in ordinary Codex configuration, outside workflow inheritance.

Store one valid local skill directory with an upstream-format `SKILL.md` per role, and freeze selected bytes and hashes. The later adapter will register/discover the exact skill metadata, use upstream explicit `UserInput::Skill` loading and verify the injected content. Extension-owned `skill://` resources use a different `UserInput::Mention` path and are deferred. No model discretion determines experimental role activation.

Run artifacts contain effective workflow data, canonical revisions, selected renderings, instruction snapshots, human edits/decisions and an ordered lab journal. Approval-critical records require checked storage synchronization before execution admission. There is no automatic live resume from files in this increment.

Later, reuse `CODEX_ROLLOUT_TRACE_ROOT` bundles for model/tool data and add actual effective Codex configuration, model catalog, task/repository/environment metadata, diff and test evidence. Tracing is best effort and has known gaps, including local compaction inference calls. Missing measurements remain unavailable; a completed turn is not a successful task or a passed test.

The eventual adapter must enforce actual write isolation for authoritative artifacts. Merely placing them outside the repository is insufficient under full-access tools. Exact controlled fields and allowed differences will be recorded so a representation comparison can reuse the very same plan.

## Upstream-sensitive files and proposed seams

Foundation changes to existing files are limited to crate membership/dependency registration in `codex-rs/Cargo.toml`, `codex-rs/Cargo.lock`, and required `MODULE.bazel.lock` / build metadata updates. It adds no lab fields to upstream config or protocol.

No planned edits to `core/src/session/turn.rs`, `core/src/client.rs`, `core/src/config/mod.rs`, `core/src/tools/registry.rs`, TUI, CLI, provider code, app-server protocol, or subagent lifecycle.

The later live milestone will evaluate one fail-closed tool-admission contributor in `ext/extension-api`, one isolated core adapter and a small call at `ToolRegistry::dispatch_any_with_terminal_outcome`. Admission must precede hook side effects and account for rewrites. Host assembly belongs in `app-server/src/extensions.rs` or a bounded embedding adapter. These are proposed future seams, not changes authorized by foundation approval.

## Self-critique applied

- Removed the temptation to build a general workflow engine/event bus: use fixed phases and existing contributors.
- Removed premature CLI/protocol/TUI work and full client bootstrap.
- Kept provider identity, role instructions, canonical plan, renderer, human authority and evaluation separate.
- Reused existing profile and trace infrastructure; do not duplicate permission or session resolution.
- Avoided claiming a model alias, workflow name, or plan file is enough for reproducibility or authority.
- Limited new traits to the renderer's demonstrated two-implementation need; future transports/evaluators remain designs rather than empty interfaces.
- Accepted fewer integrated features so the first code increment can remain isolated and honestly tested.

## Tests and current prerequisites

Use `just test -p codex-lab` for domain tests. Then run relevant existing packages:

```text
just test -p codex-model-provider-info -p codex-models-manager -p codex-config -p codex-skills -p codex-skills-extension -p codex-rollout-trace
```

Refresh/check Bazel dependency metadata, run scoped `just fix -p codex-lab` and `just fmt`, and follow repository command ordering rather than direct `cargo test`. No core/common/protocol edits or complete workspace suite are proposed. A later agent-policy integration must add real mocked Codex integration tests for direct/nested/parallel calls, hook ordering, patch/shell/MCP paths, stale approvals, amendment draining and disabled/unapproved behavior.

Windows currently has no Rust/just/Bazel on PATH. Ubuntu WSL has Rust/Cargo 1.75; this repository pins 1.95.0. Provision the pinned toolchain and required helpers after approval. No Rust tests or model requests have been run during research. Do not lower upstream's required Rust version to fit the machine.

## Muse and remaining work

Muse's provider/API/model ID remains unresolved. This checkout supports the Responses wire API and explicitly rejects `wire_api = "chat"`. Custom-provider configuration is the first option if Muse meets that contract; otherwise an external versioned adapter needs separate investigation. Unknown model metadata must not silently fall back to GPT-oriented context/tool assumptions.

Deferred: live agent workflow/approval enforcement, Muse smoke calls, upstream `--workflow`, automatic resume, TUI, GitHub/Actions/XML/compact representations, additional role variants, subagent experiments, run/compare/sweep commands and hidden-test evaluation.

Approved scope: **F01–F06 of `codex-lab-foundation` revision 1**. If further implementation discovers a need for upstream runtime modifications or a materially different gate/configuration design, return with a concrete amendment before making that change. See [`README.md`](README.md) for the implemented API and deferred work.
