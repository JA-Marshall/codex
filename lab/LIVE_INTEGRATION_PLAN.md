# Live integration milestone — revision 1

Status: **explicitly approved and implemented through G01–G06**. See `live-integration-approval.json` for authorization, `RUNNING.md` for the delivered interface, and `PROGRESS.md` for exact test results and upstream/environment exceptions. Canonical reviewed source remains unchanged: `live-integration-plan.json`, plan ID `codex-lab-live-integration`, revision 1. This approves development of the harness; it does not approve future experimental task plans.

## Outcome and stages

Deliver a restricted Linux/WSL local driver whose real Codex tool calls obey canonical-plan approval. Prove the complete workflow using mocked Responses so development does not depend on Muse credentials or the user remaining present.

1. **G01 — Dispatch admission:** introduce an optional typed contributor in `codex-rs/ext/extension-api/src/contributors/tool_admission.rs`, registration/export wiring, and a small call into a new `core/src/tools/admission.rs` helper from `ToolRegistry::dispatch_any_with_terminal_outcome`. Every contributor must admit. A non-clone RAII permit covers dispatch; denied calls never reach hooks or handlers. No contributor means existing behavior.
2. **G02 — Lab adapter:** keep policy and authority in a separate `codex-rs/lab-runtime` crate. Synchronize approval checks with revocation, bind exact targets, preserve durable journal ordering, and track active calls. Adapt the domain library only where asynchronous admission actually requires it.
3. **G03 — Restricted driver:** a separate `codex-lab` executable embeds existing `core-api`/`ThreadManager`, configuration, authentication, skills and environment APIs. Drive research, structured planning, human review/edits, implementation, verification and completion. Explicit human approval arrives through host stdin and never through a model tool. Revoke and use upstream `shutdown_and_wait` before reporting amendment paused. Fresh phase threads are acceptable and recorded consistently.
4. **G04 — Muse and evidence:** prepare configuration-first Muse Spark 1.3 Contributor setup, record verified and unknown capabilities, and reuse upstream tracing alongside lab-owned artifacts. Pin model/tier/settings and instruction bytes. No credentials are needed for mocked tests; a live test needs local credentials and its own task-plan approval.
5. **G05 — Verification:** test direct/nested/concurrent calls, stale and revoked targets, pre-hook denial, interruption/draining, skills, sandbox preflight, and a full mocked workflow for both renderers. Run targeted suites, then the full upstream workspace suite for core changes, plus required lint/format/Bazel checks.
6. **G06 — Handoff:** review upstream-sensitive changes, document results and limits, maintain the ledger, and optionally checkpoint coherent verified work in local commits. No push, deployment, purchase or account-setting changes.

## Initial runtime boundary

Support the existing Linux/Ubuntu WSL environment first. Reject unsupported hooks, MCP/plugins, implicit/native skill discovery, subagents, background/code modes, provider built-in tools and unsafe effective sandbox settings before running the task. Do not expose host `UserShellCommand` or direct MCP operations. Research uses two bounded lab read/list tools wrapping the existing `ExecutorFileSystem` and sandbox context, with canonical repository containment checks. There are no general-purpose existing built-in read/list tools to reuse directly. Arbitrary shell and unknown capabilities remain denied before approval. Do not classify shell commands by prefixes. Approval records and host input must be protected from model tools; merely storing them outside the repository is insufficient. Full-access configurations that cannot protect authority are unsupported.

Canonical output and required instruction delivery must be validated, bounded and recorded. Freeze selected role module bytes and inject them through existing `Config.developer_instructions` and its typed context fragment, using fresh phase threads. This is deterministic procedural instruction delivery; native skill invocation accounting is deferred because that loader can warn and continue after failure. Verification remains evidence driven; a model saying tests passed is not sufficient. Existing execution, sandbox, permission, authentication, Git and session machinery remain upstream-owned.

## Architectural critique and refinement

| Concern | Refined decision |
| --- | --- |
| Adding policies throughout the agent loop | One dispatch call plus an isolated helper; policy remains in the lab adapter. |
| Reusing lifecycle callbacks as a gate | They return no denial result. Add a dedicated admission contributor and keep observers intact. |
| App-server integration causes many edits | Current in-process client lacks extension injection. Embed the existing core-api facade; avoid app-server/TUI/protocol changes. |
| A counter says tools stopped while terminals still run | Revoke, call upstream shutdown-and-wait, then drain permits before publishing paused. |
| Hook or external capability bypass | Restrict the initial host and test effective preflight; admission alone is not a claim about every possible host action. |
| Confounding representation with planner/provider | Keep the same canonical plan and fixed configuration/instructions when comparing renderers; record phase thread boundaries. |
| Provider-specific core branches | Prefer documented Responses/custom-provider configuration. No adapter unless a demonstrated contract mismatch requires one. |
| Assuming research and skill seams already guarantee determinism | Add only read/list adapters over the existing filesystem service; use frozen procedural instructions through the existing developer fragment. Defer native skill invocation accounting. |
| Premature generic framework | No new generic event bus, plugin ABI, benchmark runner, GitHub renderer, TUI or subagent policy. |
| Bootstrap or isolation requires broad upstream ownership | Stop for an amendment; do not grow this plan into a runtime rewrite. |

## Approval envelope

Approval of this revision authorizes G01–G06, necessary local build dependencies, the full workspace test suite, routine fixes within these boundaries, and local checkpoint commits. Two hours is the user's AFK window, not a promised test-completion deadline. The agent continues necessary work until the milestone is complete or an actual blocking condition requires input.

Approval does not waive the experimental workflow's human gate or authorize model-generated plan amendments automatically. Live Muse calls remain pending local API credentials and a separately approved experimental task plan. The initial foundation's reviewed plan and approval record remain unchanged.
