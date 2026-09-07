# Muse provider feasibility

The selected target is **Muse Spark 1.3 Contributor**, checked against public sources on 2026-09-07. This is the data-sharing tier: Meta uses inputs and outputs submitted to it for training and improvement. Vercel documents the gateway identifier `meta/muse-spark-1.3-contributor`. The user has selected the tier; the gateway and account credentials remain unconfigured. [Vercel's announcement](https://vercel.com/changelog/muse-spark-1-3-now-available-on-ai-gateway).

Meta's cookbook documents the direct base URL `https://api.meta.ai/v1`, credential environment variable `MODEL_API_KEY`, and standard model `muse-spark-1.3`. It includes Responses API recipes. It does **not** establish that Vercel's Contributor identifier works on the direct endpoint. [Meta API fundamentals](https://github.com/meta-models/meta-model-cookbook/blob/main/01_api_fundamentals/README.md).

`muse.toml.example` is a configuration template for that direct API candidate. Its model and catalog placeholders are intentional. Confirm the exact Contributor routing/account entitlement before replacing them. A gateway configuration must use that gateway's documented base URL, authentication, and exact identifier together.

The exact catalog must also satisfy the restricted host's instruction, command-tool and ambient-capability requirements described in [RUNNING.md](../RUNNING.md). Verify the provider supports those requested tool formats before populating the catalog; a model identifier alone does not supply that contract.

At the pinned Codex baseline, `ModelProviderInfo` already accepts custom `base_url`, `env_key`, and `wire_api = "responses"`; `WireApi` rejects legacy `"chat"`. No Muse-specific core branch or protocol translation has been added. The non-OpenAI provider name avoids capability selection tied to the upstream `OpenAI` name. See `codex-rs/model-provider-info/src/lib.rs` and `codex-rs/model-provider/src/provider.rs`.

The remaining compatibility checks are an actual Responses function-call/result exchange, terminal streaming events, structured plan output, accepted tool formats/request fields, reasoning replay, usage reporting, context/output limits, and account access to the Contributor tier. Documented Responses support establishes feasibility, not a completed integration test. No live Muse request was made for this milestone.

For each run, retain the requested and reported model identifiers, provider URL and adapter version if any, exact model catalog and instruction hashes, resolved context/output/reasoning settings, retries, and enabled tools. Pin `1.3` for an experiment batch; a moving `latest` alias is insufficient. Unknown fields remain explicitly unknown until verified. Codex's unknown-model metadata fallback is unsuitable as an experimental control, so the live driver requires an exact catalog entry.

Only the credential variable name/presence belongs in shareable metadata. API keys, credential-bearing headers, authentication files, and arbitrary environment dumps must not be serialized. Detailed model/tool traces may contain the submitted repository task data and remain local. Selecting the Contributor tier does not authorize collection of unrelated files.
