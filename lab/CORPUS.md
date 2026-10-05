# Corpus provenance and access boundary

The primary design is 60 scenarios: 24 development, 12 validation and 24 confirmation, half clear-intent Track A and half evolving Track B in each split. Owner diagnostics are supplemental. They never satisfy the primary Track A quota or enter its acceptance denominator. The existing six sentinels therefore contribute three clear-A, two B and one separate diagnostic; they do not constitute a completed corpus.

`python lab/experiments/study.py corpus validate corpus.json` checks opaque metadata and prints counts. It does not open task packs or prove that calibration happened. An index contains exactly `schema_version: 1`, `id`, `state` (`draft` or `sealed`), `development_root` (one relative directory name), `custodian_seal_sha256` (nullable in a draft) and `entries`.

Each entry contains `id`, `project_id`, `lineage_id`, `duplicate_family`, `split` (`development`, `validation`, `confirmation`), `track` (`A`, `B`), `cohort` (`primary`, `diagnostic`), boolean `owner_diagnostic`, `content_sha256`, `calibration_sha256`, and `provenance`. The latter contains only `origin` (`private-authored`, `public-repository`, `synthetic`), `origin_fingerprint`, `revision_fingerprint`, and boolean `exposed_to_tuning`. Hashes use lowercase SHA-256. Content and calibration commitments may be null while drafting; selected development tasks need both. Opaque IDs and hashes convey no briefs, cases, references, owner facts or held-out paths.

Shared project IDs, declared ancestry, duplicate families, source origins and exact content form connected groups, including transitive links. Those groups cannot cross splits. Confirmation requires 24 separate declared groups, not merely 24 differently named task IDs. This detects declared relationships and exact duplicates; provenance review must still assess undeclared near duplicates and realism. Public-source training contamination remains unknown.

Keep the public index beside its development directory and a `certificates/` directory. Add `corpus_index` to the study TOML's `[paths]`; `task_root` must resolve to that exact development directory without aliases. Selected task identities, content inventories, certificate fingerprints, evaluator version and variant inventory must match. Freeze copies the index and selected certificates and binds the archived task bytes again. A changed task or grader requires recalibration. Symlinks, path aliases and linked certificate/index files fail closed.

## Authoring and calibration

Use TaskSpec v2 with a public brief and checks, private critical requirements, the reference, an irrelevant patch control, and at least two meaningful mutants. Keep `authoring.json` with the task before calibration. It contains exactly `schema_version: 1`, `task_id`, `project_id`, `lineage_id`, `duplicate_family`, and `mutant_roles`. The latter maps every mutant name to `wrong-interpretation`, `visible-test-only` or `regression`; the first two roles must be represented. The private policy declares each mutant's intended critical failures.

```sh
python lab/experiments/study.py task calibrate --root corpus/development --task TASK_ID --sandbox /absolute/codex-linux-sandbox --output /new/calibration
python lab/experiments/study.py corpus certify-development --task corpus/development/TASK_ID --authoring corpus/development/TASK_ID/authoring.json --calibration /new/calibration/calibration.json --output corpus/certificates/TASK_ID.json
```

Calibration binds task inventories and evaluator hashes, and hashes each evaluation. Certification re-reads every required result, requires the reference/alternatives to pass and baseline/irrelevant/mutants to fail, checks intended critical failures, and verifies that a visible-test-only mutant actually passed public checks. It rejects omitted rows, stale assets and inconsistent evidence. Set the index's `content_sha256` to the certificate's content commitment and `calibration_sha256` to the certificate file hash. This executable evidence does not replace review of task relevance or semantic independence.

## Held-out custody

Before authoring held-out content, establish a separate authoring/custodian context and a plaintext store outside the repository, development root and tuning archives. That context must not receive tuning failure feedback. The current implementation thread must not author or inspect sealed briefs/cases/references. Only opaque commitments are imported into its index. No sealed content has been created by this checkpoint.

The custodian keeps reference implementations, mutants and detailed calibration output private. The planned execution boundary mounts selected public starters/briefs only for an immutable, preregistered arm after a one-time reservation; existing evaluator mounts keep private cases and sibling outputs out of model workspaces. Release is one-way after terminal shutdown and the predeclared analysis boundary. Released projects become exposed regression data and cannot be reused for a new confirmation claim.

The development CLI rejects validation/confirmation before task discovery, and discovery checks every task's split before hashing or loading pack contents. Development proposal checks precede frozen payload reads. Reports reject held-out results before reading or hashing them, including queue parents. The legacy standalone task-library CLI remains for historical exposed libraries; it is not a sealed-data access interface. Historical `study` labels do not make already exposed tasks held out.

This is an application and mount boundary. It does not hide plaintext from a privileged host administrator. Stronger confidentiality requires a separately permissioned custodian. Preregistration, reservation, controlled release, the real 60-scenario inventory and sealed execution remain separate outstanding deliverables; an index with plausible hashes is not completion or launch authorization.
