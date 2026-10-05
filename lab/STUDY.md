# Study commands and recorded iteration

Run these from this checkout with Python 3.12. Freezing, task calibration and real campaign execution require the existing Linux runtime, sandbox and provider setup. `validate` is configuration preflight; `freeze` additionally verifies and pins runtime dependencies. These commands are a thin interface over the existing runner, not a second scheduler.

```sh
python lab/experiments/study.py validate study.toml
python lab/experiments/study.py freeze study.toml --registry work/variants
python lab/experiments/study.py run /absolute/path/campaign.json
python lab/experiments/study.py resume /absolute/path/campaign.json --output /new/disjoint/campaign
python lab/experiments/study.py compare /absolute/path/campaign --output /new/report
python lab/experiments/study.py task calibrate --root lab/tasks/sentinels --task py-archive-intent --sandbox /absolute/codex-linux-sandbox --output /new/calibration
python lab/experiments/study.py workflow propose revision.json --registry work/variants
python lab/experiments/study.py roadmap --intent intent.txt --proposal proposal.json --output /new/kickoffs
```

`resume` prepares a new manifest for never-started queue slots only. Run it explicitly after reviewing that manifest. Started trials retain their consumed budgets and outcomes; they cannot be restarted through this command. Terminal SDK runs require confirmed process and provider shutdown; legacy runs revalidate the original evaluator observation and journal hashes. The exclusive parent claim prevents preparing the same slots twice. Interrupted preparation leaves a claim for manual investigation, not an automatic retry. Comparing a resumed campaign includes its original parent slots with source hashes, and rejects changed conditions. Parent results are not new repetitions.

The study TOML has explicit `[paths]` entries for `binary`, `codex_home`, `catalog`, `instruction_root`, `sandbox`, `output`, `task_root`, and `provider_service`. Optional paths are `sdk_config`, `task_toolchain`, `task_just`, and `python_runtime`. Paths resolve relative to the TOML file. Use the existing reviewed runtime/settings files; do not place credentials in this file.

For an explicitly metered legacy study, omit `sdk_config` and add `[legacy_budget]` with `requests`, `tokens`, `seconds`, `input_ceiling`, and `output_ceiling`. For example, the development comparison uses 120 requests, 4,000,000 charged/reserved token units, 1,800 seconds, a 500,000-byte input ceiling, and a 16,000-token output ceiling per project. The original legacy workflow's phases share this admission ledger. The host runs inside an owned PID namespace with an absolute deadline, a fresh profile using an ephemeral proxy credential, and access only to its own repository and run directory. Grading also requires the original legacy journal/observation proof; namespace shutdown alone cannot manufacture a terminal workflow result. Queue resume revalidates both proofs and the meter receipt hash. Legacy studies without this explicit table retain their historical behavior and must not be presented as budget-matched. Owner clarification and evolving-project legacy runs remain unsupported by this command until verified.

```toml
stage = "development"
jobs = 2
repetitions = 1
max_amendments = 0
purpose = "throughput"

# Add [paths] with the actual runtime paths described above.

[[conditions]]
workflow = "our-v0"
tasks = ["py-archive-intent", "py-csv-review"]

[storage]
max_bytes = 2147483648
reserve_per_active_trial = 268435456
min_free_bytes = 1073741824
debug_bytes_per_trial = 20971520
full_trace_sample = ["trial-0001"]

[variant]
id = "our-v0-initial"
# Omit parent for a root variant; use a registered ID for a revision.
hypothesis = "Preserved intent plus one evidence-based reviewer improves delivery."
change = "Initial lean workflow baseline."
```

The sample is a schema illustration; fill in real paths before validating. Trace samples must name unique planned run IDs. The freezer's existing balanced workflow rotation assigns IDs, including gaps for omitted matrix combinations. Disk limits govern admission with reserved space for active trials, not a filesystem quota. After confirmed shutdown, selected failures and predeclared samples retain known SDK debug artifacts within the per-trial cap. Rollout JSONL files and each logs SQLite/WAL/SHM family are kept or discarded whole. The hash receipt is written before deletion. State databases, products, checks, usage, lifecycle and invocation evidence are retained. Legacy debug deletion is not implemented. No policy is applied retrospectively to historical campaigns.

A workflow revision is distinct from a product roadmap. `workflow propose` takes JSON with `id`, `hypothesis`, `incumbent_manifest`, `challenger_manifest`, and `policy_change`. Both manifests must already identify frozen development variants. `policy_change` contains `path` (relative to the frozen lab archive), `before_sha256`, `after_sha256`, and `description`. The two campaigns must have matched task/repetition slots, model/runtime/effort/budgets/interaction settings, and exactly the declared workflow source difference. This verifies one changed file mechanically; review still determines whether it is one meaningful policy. Every proposal attempt is recorded, including invalid/rejected ones. A proposal does not launch either arm.

`run` creates an exclusive attempt directory and records launch and process exit, plus the results hash when available. A missing terminal receipt is unfinished/unknown, not success. Existing campaign receipts remain authoritative. Registered variants are immutable and reference their frozen input fingerprints.

For an approved additive oracle correction, pass `--correction DIRECTORY --correction-manifest-sha256 HASH --correction-results-sha256 HASH` to `compare`. The report verifies binding to original results/candidate/evaluation and shows original and corrected acceptance separately. It never rewrites original campaign files.

This is the thin development command slice. Validation/confirmation launch remains explicitly gated; the broader calibrated corpus, held-out feedback controls, full variant search and final confirmation are outstanding. Passing CLI tests is not evidence that a workflow outperforms another.
