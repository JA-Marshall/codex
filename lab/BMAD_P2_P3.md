# P2/P3: SDK execution, workers, and metering

This stage runs the checkout's Python SDK and a locally built Codex app-server against a deterministic loopback Responses provider. It implements runtime mechanisms, not BMAD policy or benchmark scores. `run_sdk_probe.py` is the runnable offline entry point. Live campaign integration, private-grader filesystem isolation, and BMAD installation belong to P4/P5.

## Execution and stop evidence

`workflows/sdk_session.py` uses the existing typed `CodexClient`. Each worker receives a fresh thread; continuation reuses its thread ID. Thread start explicitly pins model/provider, disables fallback, disables native multi-agent dispatch and web search, and routes requests through the run relay. Supplied worker prompts are preserved. Only one writer is allowed in a group; parallel writers require the later isolated-checkout integration.

The SDK now optionally dispatches server requests through a caller-owned executor, with eight outstanding callbacks at most. Its ordinary synchronous callback behavior remains the default. Replies are bound to their originating process generation, close is serialized, and late turn registration sees a terminal transport error. The study's callback pool has bounded shutdown. An unfinished callback produces `stop_status: unconfirmed`, even if OS processes have stopped. The host-owned user-input channel supports actual question/answer callbacks and cancellation.

The Linux/WSL launcher clears inherited environment/credentials and creates private user, mount, and PID namespaces. It records the host-visible namespace-init identity and start ticks before mounting matching procfs. Matching procfs is necessary for Codex's nested sandbox: the original implementation intermittently failed with bwrap looking up a namespace-local PID in the host's `/proc`. A real shell test reproduced this; the corrected launcher passes both implementer and independent-validator tests.

Interrupt acknowledgements, completed turns, background-terminal inventory, callback shutdown, and namespace-init exit are separate evidence. Empty terminal inventory requires a valid empty array and a null pagination cursor. Namespace-init exit is the authoritative OS stop boundary: Linux kills the namespace's descendants, including detached processes and nested PID namespaces. Native Windows/macOS sessions are intentionally unsupported; use WSL/Linux, and fail before model execution when required namespace capability is absent.

Runtime pins cover the binary, local SDK Python sources, Python executable, `unshare`, and namespace launcher. `source_commit` is a build-provenance assertion, not a cryptographic proof of compilation. For this review, Codex was rebuilt from this checkout at `db0f5c188a1b37959b92c7d0f5f35f52aff9175e` plus preserved working-tree changes. The build command was `cargo build -p codex-cli --bin codex` using the existing toolchain environment below. No Rust source was changed in P2/P3.

## Worker and resource boundary

`workflows/workers.py` provides `run_workers` (one to four fresh-context workers, awaited together) and `continue_worker`. Initial HTTP calls for a group are admitted atomically. A temporary shortfall caused only by in-flight reservations waits for reconciliation; a group that cannot fit its remaining request/token envelope is rejected explicitly, without dispatching a partial reviewer group. Worker failure/cancellation stops descendant admission. Existing campaign scheduling remains responsible for the initial two-trial limit.

`workflows/metered_run.py` composes the SDK, worker bridge, and an optional observer on the existing provider proxy. Live use must point the run relay at the existing loopback shared provider service, preserving its aggregate 100-request/minute limit. The shared service's upstream credential stays in the host relay; children receive a different local relay credential and registered worker identity. Proxy retries remain disabled. Continuations and compactions pass through the same accounting boundary.

The ledger records run/worker/request attribution, observed input/output/cached-input tokens, conservative charged tokens, reservations, and unknown usage. Missing cached usage remains null. A reservation uses serialized request bytes plus 4,096 tokens of overhead and the declared output cap, subject to an input ceiling. This is a conservative text-request bound, not a verified provider tokenizer. The relay sets `max_output_tokens`; missing/invalid usage or a provider exceeding its reservation stops further admission and preserves the uncertainty. Disconnecting a remote provider cannot prove its computation stopped: missing usage is charged at the full reservation. Exact token enforcement remains dependent on provider behavior. No dollar cost is invented.

Run shutdown also waits for HTTP handlers before closing journals. Host artifacts must be separate from the candidate directory, and writable sessions exclude the default shared `/tmp` write grant. This does **not** yet establish private-grader read isolation; no live scored campaign is authorized by this stage's tests.

## Reproduce

Run in WSL Ubuntu. The base Python does not have Pydantic/pytest; `uv` supplies the pinned temporary dependency environment without installing the published Codex binary.

```bash
source /home/james/.local/share/codex-lab-toolchain/env.sh
cd /mnt/c/Users/james/Desktop/Code/trees/codex-lab-workflow-study/lab/experiments
export PYTHONDONTWRITEBYTECODE=1
export CODEX_STUDY_TEST_BINARY=/home/james/.cache/codex-lab-target/debug/codex
export CODEX_LAB_TEST_BINARY=/home/james/.cache/codex-lab-binaries/task-library-context-v3-20260907/codex-lab
uv run --no-project --python /usr/local/bin/python3.12 --with pydantic==2.13.4 --with pytest==8.4.2 python -m unittest test_sdk_workflows test_workflow_usage test_provider_proxy test_workflow_contracts test_campaign test_terminal_run test_campaign_inputs test_campaign_service test_campaign_python -v
```

Focused SDK regression command, from the repository root:

```bash
uv run --no-project --python /usr/local/bin/python3.12 --with pydantic==2.13.4 --with pytest==8.4.2 python -m pytest -o addopts="" sdk/python/tests/test_callback_lifecycle.py sdk/python/tests/test_client_rpc_methods.py sdk/python/tests/test_public_api_runtime_behavior.py sdk/python/tests/test_async_client_behavior.py -q
```

Retained offline probe, from `lab/experiments` (choose a new output directory for each attempt):

```bash
uv run --no-project --python /usr/local/bin/python3.12 --with pydantic==2.13.4 python run_sdk_probe.py --binary /home/james/.cache/codex-lab-target/debug/codex --source-commit db0f5c188a1b37959b92c7d0f5f35f52aff9175e --artifacts /mnt/c/Users/james/Desktop/Code/trees/work/bmad-plan/p2p3-probe
```

The probe saves its runtime pin, compact session and per-request ledgers, stop evidence, and final summary. Seven scripted provider responses exercise actual parent dispatch, four reviewers, and same-worker continuation. These are offline compatibility observations, not evidence of BMAD fidelity, Muse capability, product acceptance, or real-human usability.

Review logs and phase patches are under `work/bmad-plan/`. Existing P0/P1 and original dirty files remain preserved; changes are uncommitted.

Local verification: 48 affected Python tests and 29 focused SDK tests passed. The retained probe made seven mock-provider requests, observed 14 tokens, and recorded confirmed process/callback shutdown with zero unknown or in-flight requests. `just fmt` completed; unrelated formatter changes were restored byte-for-byte, and final `git diff --check` passed. These checks preceded final formatting; formatting did not change any phase-owned Python file.
