# Shared Muse request limit

## Zen first, Meta fallback

The source relay now supports OpenCode Zen before Meta. It reads `OPENCODE_API_KEY`
or the private file `~/.config/codex-lab/credentials/opencode-zen-api-key`; without
a Zen key it keeps the original Meta-only behaviour. Credentials stay outside the
repository and are never written to the event journal. This source change does
not replace the historical frozen service described below.

Zen uses `https://opencode.ai/inference/openai/v1/responses`, the current
[Console Responses endpoint](https://opencode.ai/v2/docs/console/inference).
`--zen-upstream https://opencode.ai/zen/v1` selects the legacy Zen endpoint.
The current model list is available at `https://opencode.ai/inference/v1/models`.
Meta contributor model IDs are translated to Zen's matching `-contributor-free`
IDs for Zen only; the Meta request keeps its original model and body. Free model
access may depend on Zen's policy; a rejected request falls back to Meta.

There are two Zen attempts by default (`--zen-attempts`, range 1–3), with a
30-second socket timeout (`--zen-timeout`) and up to two seconds of backoff.
Connection failures, HTTP 408/429 and server errors trigger retry, then Meta.
HTTP 401/402/403/404 trigger immediate fallback and a 60-second Zen cooldown.
`Retry-After` is respected: waits over two seconds skip directly to Meta and keep
Zen on cooldown for the requested duration. Meta still uses the shared paced
limiter; its errors remain visible to the caller. Each new request starts with
Zen unless its cooldown is active. Compaction and unsupported models use Meta.

The first opened response stream is relayed immediately and never replayed after
partial output. Invalid-request HTTP 400 responses remain visible. Local
authentication is checked before either provider is called. `/health` reports
whether Zen is enabled. The original startup cooldown still applies to Meta.

Run the regression coverage without contacting either live provider:

```sh
cd lab/experiments
python3 -m unittest test_provider_proxy test_provider_failover -v
```

The historical frozen-service instructions follow.

Observed setup on 30 September 2026: the updated relay is running at the same
`http://127.0.0.1:8765/v1` address from
`/home/james/.cache/codex-lab-provider-proxy/zen-20260930`. That directory contains
the copied source, `service.json`, metadata-only `events-*.jsonl`, and
`live-validation.json`. Restart it with
`python3 /home/james/.cache/codex-lab-provider-proxy/zen-20260930/run.py` while
port 8765 is free. It is a detached process with no automatic boot restart.

The inference-only Zen key is private at the credential path above (mode 0600).
The live test observed Zen HTTP 403 (`FreeTierError`: free models can only be used
from within OpenCode), followed by Meta HTTP 200 with a completed `OK` answer.
The free Contributor model is therefore currently unavailable through this relay.
Funding alone does not change that free-model restriction; using paid Zen models
would also require selecting a paid model. No credits or payment method were added.

This machine's configured lab home is
`/home/james/.config/codex-lab/muse-contributor-limited`.
Use it for future preparations. The frozen service is installed at
`/home/james/.cache/codex-lab-provider-proxy/v1-20260907`, listening on port 8765.
Its local `service.json` records the PID/config/source identities; `events.jsonl`
contains metadata. The [setup receipt](rate-limit-setup-20260907.json) is a snapshot,
not a promise that the process survives logout/reboot. It has no automatic restart.
The original direct home and cancelled campaign artifacts remain unchanged.

All parallel workers must use **one loopback proxy** for the same Muse account.
The proxy permits at most 100 upstream request writes per rolling minute and
paces them at least 0.6 seconds apart. Response streams overlap: sixteen workers
can remain active while new requests wait their turn. A client retry consumes
another slot. This is a request limit, independent of token or concurrency limits.

Run in the same WSL environment as the lab hosts, with `MODEL_API_KEY` already
available in the process environment (never place its value in the command line):

```sh
python3.12 lab/experiments/provider_proxy.py \
  --requests-per-minute 100 --port 8765 \
  --upstream https://api.meta.ai/v1 \
  --events /absolute/path/to/new-provider-events.jsonl
```

Use the existing custom-provider configuration in a **new dedicated Codex home**:

```toml
[model_providers.muse-lab]
name = "Muse lab provider"
base_url = "http://127.0.0.1:8765/v1"
env_key = "MODEL_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
```

Keep the other model/catalog/context settings from `muse.toml.example`. All runs,
planners and compaction requests must use that same home/URL. Do not start one
proxy per worker. Do not change the config or binary of already sealed preparations;
prepare fresh targets so the effective provider URL is bound into human approval.
Old direct-to-Muse profiles and other applications bypass this limiter. Account
traffic outside this proxy still shares Muse's allowance; lower the configured
rate if necessary. The option accepts 1–100, never more than the stated ceiling.

The proxy starts with a 60-second cooldown on every restart, avoiding a fresh burst
while requests from its previous process may still occupy the provider window.
`GET http://127.0.0.1:8765/health` checks local readiness without calling Muse.
On a 429, the proxy forwards the response unchanged and pauses the shared queue
according to `Retry-After` (seconds or HTTP date); absent/invalid headers mean 60
seconds. A 503 with `Retry-After` also pauses the queue. Already dispatched requests
cannot be recalled. Provider-side arrival timing or other limits can still cause
429s; they remain visible to Codex and in the metadata log.

Only POST `/v1/responses` and `/v1/responses/compact` are relayed to the fixed
upstream. Credentials are validated locally and sent upstream over HTTPS; request
bodies, authorization headers and response bodies are not logged. The proxy does
not rewrite model instructions or responses. SSE bytes stream through immediately.
There is a bounded 64-handler capacity and 64 MiB request-body limit. Disconnected
queued callers are removed before dispatch. Stop the proxy to stop its service;
it does not restart or resume experiments.

JSONL events record the policy, proxy source digests, client correlation IDs,
request queue/dispatch/finish times, statuses, cooldowns and cancellations. Save
this log alongside the frozen proxy scripts, upstream URL, effective config and
run trace when comparing campaigns. No Codex core, HTTP client, retry policy,
authentication implementation or workflow state-machine changes are needed.

Validation uses a local mock upstream: sixteen concurrent clients share one
paced window; 429 cooldown affects the next client; no hidden retry; SSE delivery
before completion; queued cancellation; auth/route refusal; rolling-window and
restart behavior; numeric/date/invalid `Retry-After`. No live Muse calls are needed.
