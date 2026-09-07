# Running the restricted workflow laboratory

`codex-lab` is the experimental executable in `codex-rs/lab-runtime`. It embeds upstream Codex thread management, model/provider configuration, tool execution, sandboxing, authentication and shutdown. The separate `codex-rs/lab` library remains the canonical plan/configuration/approval foundation. Ordinary upstream Codex invocations do not opt into this host automatically, and no upstream `codex --workflow` flag has been added.

This first runtime targets Linux, including the prepared Ubuntu WSL environment. Current validation results and outstanding checks belong in [PROGRESS.md](PROGRESS.md). Live Muse Contributor inference and command execution passed; the first approved workflow run failed its verification-reference check. See [the live report](providers/MUSE_VALIDATION.md).

## Before starting a task

Use a clean, committed evaluation repository and its full 40- or 64-character Git commit identifier. Tracked changes and non-ignored untracked files reject the initial baseline. Pass the repository root itself, not a subdirectory. Submodules are unsupported. Keep the repository quiescent during host evidence capture; the driver shuts down its own phase threads but cannot prevent unrelated user processes from editing files.

Create a dedicated Codex home and an artifact parent directory outside the evaluation repository. The home and artifact directories must already exist; neither may contain or be contained by the task repository. Runtime binaries/helpers must also live outside the model-writable repository. The host validates effective managed permissions and probes real filesystem writes to confirm authority files remain protected. Unsupported full-access settings or an unavailable sandbox cause failure before a model call.

Put provider configuration in the dedicated home's `config.toml`. An explicit custom Responses provider and a single exact model catalog entry are required. For Muse, start from [providers/muse.toml.example](providers/muse.toml.example) and read [the feasibility notes](providers/README.md). Direct Contributor inference is confirmed as `muse-spark-1.3-contributor` at `https://api.meta.ai/v1`. Copy the [tested restricted catalog](providers/muse-contributor.models.json) into that home and configure its absolute path. Keep the exact Contributor identifier. Configure the API key through its environment variable locally; do not put the key in the task, plan, workflow file or artifact metadata.

The model catalog must match the configured model ID exactly. Codex's unknown-model fallback is rejected. The supplied Muse catalog distinguishes documented/measured capabilities from chosen harness restrictions in its accompanying provider notes. Provider selection and workflow selection remain independent.

The catalog is an upstream `ModelsResponse` JSON object with exactly one entry in `models`. That entry needs either `model_messages.instructions_template` or the supported legacy `base_instructions` field, a positive context window, and `shell_type = "unified_exec"` so verification can collect command evidence. The host disables resumable unified execution separately and uses upstream one-shot execution. Set `include_skills_usage_instructions`, `include_plugin_usage_instructions` and `include_apps_usage_instructions` to `false`; the last field otherwise defaults to `true`. Direct patch availability requires a verified `apply_patch_tool_type = "freeform"`; without it, implementation can use approved command execution. See `codex-rs/protocol/src/openai_models.rs` for the complete current schema and `codex-rs/lab-runtime/src/preflight.rs` for the restricted profile checks. These are host requirements, not claims about Muse's supported capabilities.

The host records the configured model ID and catalog digest. It does not independently verify the provider's serving revision; `observed_version` remains unavailable. Pinning configuration alone cannot establish that an external provider used unchanged weights or serving settings.

## Build and run

The existing Windows checkout is `C:/Users/james/Desktop/Code/trees/codex-lab`. Its Ubuntu LF verification mirror is `/home/james/.cache/codex-lab-verify`; do not treat that mirror as a separate source of edits. From PowerShell, synchronize the authorized source changes with:

```powershell
wsl -d Ubuntu --exec python3 /home/james/.local/share/codex-lab-toolchain/sync-verify.py
```

Then, inside Ubuntu:

```sh
source /home/james/.local/share/codex-lab-toolchain/env.sh
cd /home/james/.cache/codex-lab-verify/codex-rs
cargo build -p codex-lab-runtime --bin codex-lab
cargo build -p codex-bwrap --bin bwrap
install -D -m 0755 "$CARGO_TARGET_DIR/debug/bwrap" "$CARGO_TARGET_DIR/debug/codex-resources/bwrap"
```

The prepared toolchain keeps build products in `/home/james/.cache/codex-lab-target`, outside the checkout. It does not alter system Rust or shell profiles. On another machine, use the repository's pinned toolchain and keep build outputs/helpers outside the repository being evaluated. Use `just test` for tests, following `AGENTS.md`; do not run `cargo test` directly or start competing Cargo commands while the build coordinator is active.

The Linux distribution must include the upstream `bwrap` executable in `codex-resources/bwrap` beside `codex-lab`, or provide a compatible system `bwrap` through the fixed tool `PATH`. The commands above package the exact upstream workspace implementation for this debug build. Copy the resource directory when relocating the executable; building `codex-lab` alone does not package this dependency. Sandbox startup fails if neither resource nor system executable is available. Building `bwrap` requires a C toolchain, `pkg-config`, and libcap development headers. The broader upstream test suite also requires ALSA development headers on Linux and builds its own standalone `codex-linux-sandbox` helper; see `.github/workflows/rust-ci-full-nextest-platform.yml` for the maintained CI prerequisites.

Full workspace builds also include the existing voice helper, whose native bindings require GStreamer 1.28 or newer. The prepared WSL environment has an isolated prefix built from the repository's checksum-pinned `third_party/voice/sources.json` and unchanged `build_native.py` recipe. Source `/home/james/.local/share/codex-lab-toolchain/voice-env.sh` after `env.sh` before those builds/tests; it supplies pkg-config and shared-library search paths for GStreamer 1.28.6 and GLib 2.88.3. Build receipts and logs remain under `voice-build-v1` beside that script. This is development tooling for the upstream workspace, not an additional dependency of the restricted lab executable.

That voice build disables GStreamer's registry. Its existing decoder test fixture additionally needs `CODEX_TEST_VOICE_RUNTIME=/home/james/.local/share/codex-lab-toolchain/voice-build-v1/prefix` to load the built plugins explicitly. This setting applies to the decoder fixture, not the ignored packaged-runtime tests that require a separate runtime manifest. See the ledger for other full-suite environment findings and focused rechecks.

After configuring credentials/catalog and preparing a concise UTF-8 task file, the CLI shape is:

```sh
/home/james/.cache/codex-lab-target/debug/codex-lab \
  --repository /home/james/experiments/task-repo \
  --commit <full-pinned-commit> \
  --codex-home /home/james/experiments/lab-home \
  --runs-directory /home/james/experiments/runs \
  --run-id task-001-md \
  --task-file /home/james/experiments/task.txt \
  --workflow-catalog /home/james/.cache/codex-lab-verify/lab/workflows/foundation.toml \
  --instruction-root /home/james/.cache/codex-lab-verify/lab \
  --workflow plan-md-v1
```

Replace the angle-bracket commit placeholder before executing this example. Every flag shown is required. `--plan-file /absolute/path/plan.json` is optional. There is no automatic approval flag, resume flag, run-count flag, comparison command or parameter-sweep command in this milestone. Successful execution prints a JSON result containing artifact path, workflow state and phase-thread count. A nonzero exit is not successful completion; inspect its recorded state/evidence and the error.

## Human review and amendments

Without `--plan-file`, the host runs repository research and structured planning, writes the canonical revision and selected representation, then displays the review prompt. **Implementation cannot begin until a human approves the displayed target.** While waiting for human input, there is no live research/planning thread continuing in the background.

The prompt includes the complete approval target: run identity, plan identity/revision, canonical content digest and effective run-specification digest. Enter one of:

```text
approve <exact-displayed-content-sha256>
reject <reason>
edit /absolute/path/to/revised-plan.json
abort
```

Bare `yes`, a stale content digest and model-generated approval prose do not approve a plan. EOF or an empty response aborts review. A human edit must be valid canonical JSON, preserve the plan ID and increment the revision by one; retired step IDs cannot be reused. Editing `PLAN.md` alone changes no authority. After a valid JSON edit, the host displays the new revision and requires another explicit approval. Rejection returns to planning with the human's reason.

An invalid review command, stale approval digest or invalid JSON edit fails the run instead of repeating the prompt. The initial host has no resume path; inspect the diagnostic artifacts and use a new run ID after correcting the input.

If implementation or verification discovers that the approved plan is invalid, `lab_request_amendment` revokes further admissions and requests cancellation. The host uses upstream shutdown/draining before it reports the amendment boundary, generates a revised plan and asks for fresh approval. Already-performed changes are not rolled back automatically. Failure to stop or record evidence is a failure, not a claim that the workflow is safely paused.

Library embeddings must await `execute_run`/`run_phase` to completion and request cancellation through the gate. Dropping their futures or terminating the host process does not provide an awaited cleanup or safe-resume guarantee. Graceful completion requires upstream waiter success and its explicit shutdown marker; shutdown errors invalidate the phase.

Approval of the fork's implementation milestone authorizes development and tests of this host. It does not preapprove future model-generated task plans. A new experimental run started while the user is AFK waits for its human review; neither a timer nor prior blanket permission supplies its missing approval.

## Controlled representation comparisons

`plan-md-v1` and `plan-json-v1` inherit the same workflow settings and differ only in `plan.renderer`. To hold the canonical plan fixed, use the same revision-1 `--plan-file` for separate runs with different workflow selectors and fresh run IDs. This skips research/planning generation for both runs and still requires a new exact-target human decision for each run. A fresh run requires its initial revision to be 1; an old amendment revision cannot be silently imported as an already-approved continuation.

Start each run from the same clean repository commit. Keep task bytes, provider/model/version/catalog, instruction modules, context/output/reasoning settings, toolchain and other effective settings fixed. Reusing a repository after the first run without restoring a clean baseline is rejected; the host does not reset, commit or create worktrees for you. Compare saved effective inputs as well as results. Fresh phase-thread boundaries are recorded and should remain constant across conditions.

Representation is never used to reconstruct authority. Each run retains canonical `plans/<revision>/plan.json` and a separate Markdown or JSON view. Human edits produce a new canonical revision and are themselves an experimental intervention.

## Supported execution boundary

Each research, planning, implementation and verification phase starts a fresh upstream thread. Frozen planner/executor/verifier module bytes are injected deterministically through existing developer instructions. Native skill invocation/discovery is disabled: these are procedural instruction modules, not duplicated implementations of the upstream skill parser.

Research/planning admit only `lab_repo_read` and `lab_repo_list`, wrapping the invocation's upstream filesystem service and sandbox context. Reads require repository-contained regular UTF-8 files of at most 32 KiB on disk. Both tools also enforce an **8 KiB serialized response ceiling**, or a smaller budget supplied by the upstream call; JSON escaping and metadata count toward that ceiling. A file that exceeds the response ceiling returns an error without silent content truncation. Listings return at most 128 immediate entries, omit symlinks/special files and report truncation. Canonical containment supplements the executor sandbox. Upstream directory walking may enumerate/sort names internally before applying its result limit.

Approved implementation admits repository reads, `apply_patch`, foreground one-shot `exec_command` and the amendment tool. Verification admits reads, one-shot execution and amendments. It receives workspace-write sandbox permissions because tests may create outputs; this profile does not claim that arbitrary test commands are semantically read-only. Tool networking and permission escalation are disabled. The shell environment inherits no arbitrary host variables or shell profile, and receives a fixed `PATH` of `/usr/local/bin:/usr/bin:/bin`; required build tools must be available through those controls or explicitly approved command paths.

Admission enforces workflow phase and tool capability. A plan's `affected_files` is descriptive metadata, not a mechanically enforced file allowlist, and `completed_steps` records the model's implementation report. Semantic plan conformance and undisclosed deviations require later reviewer/evaluator work.

Ambient `AGENTS.md`/project instructions, implicit/native skills, hooks, MCP, plugins, subagents, memories, provider web tools, Code Mode, background/unified execution and alternative interactive approval/input paths are unsupported. Project configuration is ignored by this host; effective managed requirements are validated and cannot be silently relaxed. Unknown capabilities are denied at the dispatch boundary. These restrictions define the first reproducible profile; they are not changes to ordinary upstream Codex behavior.

## Bounds, artifacts and interpretation

The canonical foundation permits larger plans than the first live profile can inject. Each role-instruction fragment and each assembled task/plan prompt must fit **8 KiB**, with **16 KiB combined**. The prompt budget includes host wording, task, research/feedback and rendered plan as applicable. Oversized content fails instead of being silently summarized or truncated, which could confound representation comparisons. CLI task input is limited to 8 KiB; canonical JSON and workflow input to 64 KiB. The stricter assembled-prompt limit still applies.

The restricted profile also caps custom effective base instructions, the custom compaction prompt, selected catalog approval/permission text and the serialized output schema at 8 KiB. Base instructions use upstream personality expansion and override precedence before checking. These checks constrain the laboratory's inputs and custom configuration; they do not replace upstream context management or impose a new universal limit on every upstream-generated history item.

The host permits up to 32 phase threads, limits a running phase to 30 minutes, and bounds collected phase events to 10,000 and 4 MiB. Individual files written under `evidence/` are limited to 8 MiB, including JSON serialization overhead. Those files are created once, synchronized, and never overwritten. The append-only runtime journal has a 16 KiB record limit; no total journal or run-storage quota is implemented. An evidence error closes that store instance and prevents successful continuation; partial artifacts remain diagnostic, not resumable authority. Runtime shutdown is deliberately allowed to finish rather than being abandoned at the phase timeout.

The run directory includes foundation configuration/instruction snapshots, canonical plans and views, human decisions, `events.jsonl`, and `runtime-events.jsonl`. Its `evidence/` directory contains `runtime-manifest.json`, effective settings, environment metadata, numbered phase inputs/outputs, `final.diff`, Git metadata and metrics or failure evidence. The root `manifest.json` describes the independent domain library's capabilities; `evidence/runtime-manifest.json` identifies the live host's enforcement, trusted review boundary, event locations and lack of resume support. Read both scopes instead of interpreting the offline domain manifest as the runtime's capability declaration. Filenames are collision-refusing; choose a new run ID after failure. There is no executable crash-resume path.

Set `CODEX_ROLLOUT_TRACE_ROOT` to a host-owned directory outside the task repository before starting the executable to enable upstream detailed inference/tool traces. Its configured location is recorded. Upstream tracing is best effort and may omit local compaction inference; absent trace data is not zero model activity. Detailed phase/trace artifacts can contain submitted task data. The host does not dump arbitrary environment variables or authentication files.

`planner_phases` counts fresh planning threads. A phase can contain several inference calls, so `planner_calls` and `tool_calls` remain unavailable until a complete trace aggregator is attached; phase counts are not substituted for those measurements.

Final Git evidence uses a pinned base, disables external diff/textconv/clean/process/fsmonitor helpers, retains binary patches and includes non-ignored untracked regular files. Ignored untracked files are explicitly excluded. Submodules, untracked symlinks/special files, a changed HEAD, oversized capture or a capture deadline failure are rejected. Git evidence capture does not stage files, modify the index or create commits. Its aggregate output budget is 8 MiB and its deadline is 30 seconds.

Verification joins model-selected criterion/call references to actual host-observed completed command events. Invented call IDs, duplicate completion records, unknown/missing criterion coverage, nonzero exits and failed/declined command status cannot establish passing evidence. A real zero-exit command still does not prove that the command adequately tests the promised behavior: semantic adequacy remains a human reviewer/evaluator responsibility. Hidden-test success, task success and undetected plan deviations are not inferred from the model saying it is done. Consult the explicit unavailable fields in metrics rather than treating them as zeros or successes. Metrics record `verification_ready` before final completion; the terminal workflow journal event is authoritative for completion, so a later synchronization failure cannot be mistaken for a completed run from metrics alone.

## Source map for continuing work

The CLI is `codex-rs/lab-runtime/src/cli.rs`; orchestration is `driver.rs`; trusted review is `review.rs`; admission/revocation is `authority.rs`; upstream embedding/shutdown is `backend.rs`; configuration and permission checks are `bootstrap.rs` and `preflight.rs`. `repository_tools.rs`, `reports.rs`, `evidence.rs` and `git_evidence.rs` own their bounded adapters. The small upstream admission seam is documented in [LIVE_INTEGRATION_PLAN.md](LIVE_INTEGRATION_PLAN.md). Use the [progress ledger](PROGRESS.md) for approved scope, exact validation results, build logs and outstanding work before changing these boundaries.
