# Codex workflow laboratory: foundation v1

For the new restricted live host, see [RUNNING.md](RUNNING.md). The material below records the original offline foundation milestone; its statements about runtime integration and upstream edits describe that earlier scope. Current validation and remaining work are tracked in [PROGRESS.md](PROGRESS.md).

The approved follow-up in [NEXT_STEPS.md](NEXT_STEPS.md) is implemented: durable prepared-plan review, an evaluated fixture, and a Markdown/JSON pilot. The new commands and contracts are documented in [EXPERIMENTS.md](EXPERIMENTS.md). [Pilot results](pilot/RESULTS.md) record a Markdown workflow failure and a JSON candidate correctness failure; the comparison is descriptive, with no renderer winner.

[Failure measurement and varied tasks](MEASUREMENT.md) extend the external evaluator to safely stopped failed runs and add dependency-ordering and configuration-merging fixtures. New live task implementations retain their separate human plan approval gates.

[Parallel batches](PARALLEL.md) launch independent prepared hosts with a configurable job limit and separate live review channels. Approval and amendment waits do not occupy execution slots or block unrelated approved conditions.

The foundation is implemented in [`codex-rs/lab`](../codex-rs/lab). It is an offline Rust library for experiment configuration, canonical plans, representations, human decisions and recording. It does not yet intercept live Codex tools, call Muse, or add an upstream `--workflow` flag.

The approved scope and source investigation are retained in [`implementation-plan.json`](implementation-plan.json), [`APPROVAL.json`](APPROVAL.json), [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`PROGRESS.md`](PROGRESS.md). The reviewed implementation plan is intentionally unchanged; current progress lives in the ledger.

## Try the offline walkthrough

From `codex-rs`, using the repository-pinned Rust toolchain, create an artifact directory outside the evaluated repository and run:

```sh
mkdir -p /tmp/codex-lab-runs
cargo run -p codex-lab --example inspect -- \
  --catalog ../lab/workflows/foundation.toml \
  --base ../lab \
  --workflow plan-md-v1 \
  --plan ../lab/examples/plan.json \
  --output /tmp/codex-lab-runs \
  --run-id markdown-example \
  --repository-commit 112be0bd74ce327788613f4f8f92e8b7c92447c7
```

For JSON, use `--workflow plan-json-v1 --run-id json-example` with all other arguments unchanged. The example binds the supplied repository metadata; it does not verify or modify that repository. It prints the pending review state and artifact path, then exits. Existing run IDs are refused, including partially written runs. The example has no automatic approval flag.

The commands work with equivalent native Windows paths and an existing output directory. Actual validation in this session uses an isolated Ubuntu WSL toolchain and LF checkout mirror; native Windows execution is not claimed. See the ledger for exact commands and outcomes.

## What is implemented

| Area | API / files | Behavior |
| --- | --- | --- |
| Canonical plan | `PlanRevision`, `PlanStep`, `PlanCriterion`; `src/plan.rs` | Schema/version validation, stable step IDs, acyclic dependencies, criterion references, portable affected paths, deterministic JSON and SHA-256. |
| Representation | `PlanRenderer`, `MarkdownRenderer`, `JsonRenderer`; `src/render.rs` | Pure bounded projections of the same plan; no approval or network side effects. |
| Workflow configuration | `WorkflowCatalog`, `ResolvedWorkflow`; `src/config.rs` | Strict TOML, one-parent inheritance, explicit role/renderer selectors and effective configuration. |
| Role instructions | `InstructionSnapshot`, `RoleInstructions`; `src/instructions.rs` | Exact local `SKILL.md` selection, containment, size/hash checks and immutable byte snapshots. |
| Workflow | Private reducer in `src/workflow.rs`; exported state/target/evidence types | All eight phases, exact approval binding, edits/rejection/amendments, dependency progress and evidence-gated completion. |
| Recording / admission | `RunSpec`, `LabRun`; `src/run.rs` | Single-writer artifacts, synchronized human decisions, checked synchronous action admission and failure handling. |

No existing runtime source file is changed. Existing-file edits are one Cargo workspace member and its lockfile package entry. The new Bazel package follows the existing `codex_rust_crate` macro. The dependency set is already present upstream, so the Bazel lock refresh produces no lockfile change.

## Canonical plans and representations

[`examples/plan.json`](examples/plan.json) is a complete schema-v1 input. `PlanRevision` holds the immutable specification: identity/revision, goal, assumptions, steps, files, dependencies, risks, acceptance criteria, verification strategy, discoveries and blockers. A run owns its copy and exposes only a shared reference. `StepProgress` and verification evidence live outside that specification.

Canonical encoding sorts object keys recursively, retains array order, preserves string contents, and writes compact UTF-8 JSON with one final LF. A digest changes if approved specification content changes. Step progress does not change the plan digest. Schema-v1 limits are 128 items per collection, 8,192 bytes per text field, and 65,536 canonical bytes. Affected paths use `/` and reject traversal, absolute paths, drive/stream syntax and portable reserved names.

Both renderers preserve every specification field. The Markdown renderer uses headings/lists with JSON-quoted text in protected code spans, including explicit escapes for newlines and HTML-sensitive characters. This is a deliberately lossless first representation; more natural Markdown can be a separately versioned experiment. Rendered Markdown has a 524,288-byte ceiling. These are artifact limits, not claims about model-context fit; no context injection exists yet.

Every plan revision is written to `plans/<revision>/plan.json`. The selected projection is `PLAN.md` or `plan.view.json` in the same directory. Editing a projection does nothing to workflow authority. Human changes use `edit_plan` with an editor/reason, increment the revision, retain the plan ID, and require fresh approval. Removed step IDs cannot be reused. Replacement revisions conservatively reset all progress and verification evidence.

## Configuration and deterministic instructions

[`workflows/foundation.toml`](workflows/foundation.toml) contains a common `plan-base` workflow and two children. The resolved behavioral settings of `plan-md-v1` and `plan-json-v1` differ only in `plan.renderer`; their names/inheritance provenance remain separately recorded.

The schema requires `schema_version = 1`, `[workflows.<name>]` and `[skills.<selector>]` tables. Child scalar settings replace their parent's settings; omitted nested fields preserve siblings. There are no list-valued workflow settings in v1. The parser rejects unknown keys, unsupported enums, inheritance cycles, missing parents, catalogs over 64 KiB and chains deeper than 16. Resolution requires all three roles, a renderer and `approval = "human_required"`; there is no automatic approval mode.

Each skill catalog entry supplies a relative local directory and lowercase SHA-256 of its `SKILL.md`. Paths are relative to the explicit `--base`, never inferred from a process working directory. Reads reject missing files, nonlocal/escaping paths, out-of-base symlinks, empty or oversized content, non-UTF-8 and hash mismatches. Selected snapshots are immutable and bounded to 12 KiB each. The sample skill subtree pins LF line endings so checkout conversion does not invalidate hashes.

The three shipped skills have upstream-format frontmatter. This library intentionally does not duplicate Codex's discovery/frontmatter parser or inject instructions. The later adapter must register/discover those exact local skills, use `UserInput::Skill`, and verify actual injection without truncation or fallback. `skill://` resources have a different upstream `UserInput::Mention` path and remain deferred.

Model/provider settings are outside workflow TOML. `RunSpec` records the task, repository commit/initial dirty-patch digest, optional non-secret model metadata, selected workflow/provenance and frozen instructions. Its digest uses versioned fixed struct field ordering. Construct it with `RunSpec::resolve`; it cannot be deserialized or modified into execution authority. The exact source catalog is recorded separately; only effective selected inputs enter the run-spec digest.

## Approval and execution contract

`LabRun` is the public facade. Typical host sequence:

```text
create -> researching
begin_planning -> planning
submit_plan -> awaiting_plan_approval
approve(exact_target, human_reviewer) -> implementing
perform(exact_target, Implementation, synchronous_action)
record_step(... evidence ...)
begin_verification -> verifying
perform(exact_target, Verification, synchronous_check)
record_verification(... host evidence ...)
complete -> completed
```

The host must obtain a real human decision before calling `approve`. The library cannot establish that a person was present; the method must never become a model-visible tool. `ApprovalTarget` binds run ID, plan ID, revision, canonical-content hash and run-spec hash. A matching target alone is insufficient: the current in-memory state must contain its explicit approval. Run-ID uniqueness across separate artifact roots is a host responsibility.

`perform` rechecks current authority and synchronizes an admission event before invoking the supplied closure. It issues no reusable permit. The mutable borrow serializes operations on this single run during the synchronous call. An action error/panic or recording failure revokes authority; a host panic is rethrown even if recording also fails. No claim is made about detached processes or asynchronous work started by that closure.

Initial rejection returns to planning; the replacement revision needs a new decision. `request_amendment` revokes approval, clears the pending target and enters `awaiting_plan_amendment`. A new revision must be submitted before approval can be reconsidered. Rejection of an amendment remains paused. An explicit later human decision can approve that pending revision. Material strategy changes require amendments; the library does not semantically detect every deviation.

Step dependencies must be complete before dependent work progresses, completed steps need evidence, and progress cannot move backwards. Verification starts only after all steps complete. Completion requires a passing observation for every verification check and evidence covering every acceptance criterion. Evidence references are host-supplied observations, not independent proof of test success; test execution and evaluation remain separate future adapters. Failed and completed runs are terminal.

## Artifact and failure behavior

```text
<run-id>/
  manifest.json
  config/{run-spec.json,workflow.source.toml,workflow.effective.json}
  instructions/{planner,executor,verifier}.SKILL.md
  plans/<revision>/{plan.json,PLAN.md or plan.view.json}
  decisions/<sequence>.json
  verification/<sequence>.json
  events.jsonl
  metrics.json
```

Journal records have a sequence, UTC milliseconds, monotonic elapsed milliseconds, typed change, phase and current approval target. Changes carry deltas rather than repeating the entire progress map. Individual journal records are capped at 256 KiB; there is no total run quota yet.

The reducer applies a proposed change to a private clone. Referenced new artifacts are created without overwrite, written and synchronized before the event; the event is appended and synchronized before publishing the new state. Unix also synchronizes parent directories when creating names. Windows uses file synchronization; no cross-platform crash recovery or live resume is implemented. An I/O failure can leave partial artifacts, but never releases new authority. There is no API for reopening them into an executable run.

Treat interrupted/partially recorded runs as incomplete. A file named `decisions/…` is not sufficient evidence of a committed transition: the corresponding synchronized journal event and consistent referenced artifacts are required. Even a complete journal is review evidence only in this release; no restore API exists. Locating records outside the repository is organizational separation, not a security boundary. A live adapter must verify sandbox/host isolation that prevents model tools from modifying authoritative records.

The foundation collects only explicit lab inputs and observations. It does not dump environment variables or credentials. Its typed model metadata has no auth fields; do not put secrets in human-authored catalogs or instruction files, whose exact contents are intentionally preserved. `metrics.json` marks unavailable evaluator/token/tool measurements as `null`. It does not fabricate success from a completed domain transition.

## Reproducibility and the next integration

Reuse upstream `CODEX_ROLLOUT_TRACE_ROOT` and its reducer for model/tool/code-mode/terminal/subagent evidence. Tracing remains best effort, with local compaction inference and resumed-child limitations. The future adapter must record effective Codex config and provenance, exact model catalog/instructions, auxiliary model settings, context/compaction controls, environment/repository evidence, verification results and final diff. Provider aliases are not immutable model versions.

The target is now Meta Muse Spark 1.3 Contributor, following the user's latest-release/data-sharing-tier selection. Meta's cookbook documents a Responses endpoint, making a custom provider with a verified static catalog the first integration path. Contributor access/identifier and the complete Codex tool/streaming contract still need verification. No live request was made. See [Muse feasibility](ARCHITECTURE.md#muse-feasibility) for dated evidence and remaining checks.

The next milestone needs a small fail-closed dispatch-admission contributor and integration tests for direct/nested/parallel tools, hook ordering, patch/shell/MCP paths, stale authority and amendment interruption/draining. Existing tool lifecycle callbacks cannot veto, command hooks are optional and can fail open, and client-side turn scheduling alone is insufficient. Preserve the existing sandbox, authentication, execution and subagent lifecycle. Amend the plan before touching those deferred runtime seams.

Additional representations, procedural variants, TUI, live resume, benchmark run/compare/sweep commands and hidden-test evaluation remain deferred.

## Validation and review boundaries

Use the repository helpers:

```text
just test -p codex-lab
just test -p codex-model-provider-info -p codex-models-manager -p codex-config -p codex-skills -p codex-skills-extension -p codex-rollout-trace
just bazel-lock-update
just bazel-lock-check
just fix -p codex-lab
just fmt
```

Validation completed: **33 foundation tests and 656 relevant upstream tests passed, with no skips**. Both offline representation examples passed; strict Clippy, format checks and Bazel lock/target checks passed. Native Windows and Bazel test execution were not run.

The tests exercise invalid plans/configuration, renderer preservation/snapshots, mandatory instruction failures, approval targets across all phases, amendments, verification, artifact collisions, edited projections and recording faults before/after actions. They use temporary directories and fake synchronous actions; none invoke models.

For review, inspect schema/rendering first (F01), then configuration/instructions (F02), then the private state reducer and recording facade together (F03/F04), then the offline example (F05). F03's integration tests depend on F04's public facade. These module boundaries identify smaller review stages without scattering changes into upstream runtime files. Exact verification results and toolchain/mirror paths are recorded in the progress ledger.
