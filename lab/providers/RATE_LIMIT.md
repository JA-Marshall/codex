# Shared Muse request limit

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
