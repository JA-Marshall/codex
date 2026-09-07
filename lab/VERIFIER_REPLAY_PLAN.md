# Fixed-candidate verifier trials

Approved scope: prepare five trials for each of the two verifier instruction
variants against the same passing candidate, then obtain exact human decisions
before model execution. Use bounded parallel hosts, not parallel agents. Keep
the original experiments and their approvals immutable.

## Findings and refined implementation

`lab-runtime/src/driver.rs::run` always executes an implementation phase before
verification. `review_prompts` supplies task and rendered plan to a fresh verifier
thread; no prior executor conversation is restored. `reports::verification_evidence`
validates real command receipts. `prepared.rs` seals pending input inventories;
`prepared_launch.rs` revalidates settings, pins and the clean Git baseline under
a per-checkout lock. `lab/src/run.rs::RunSpec` binds effective inputs to human
approval. `run_batch.py` already accepts up to 32 isolated pending hosts and bounds
active jobs without blocking on other reviews.

1. Add a bounded, explicit `VerificationInput` data object in a new lab-runtime
   module. It contains the candidate commit, canonical plan hash, source-run/phase
   provenance and the fixed implementation report. Validate plan/commit/report
   identity; this is input evidence, never saved authority or test success.
2. Add `--verification-input` requiring `--plan-file`, with an optional RunOptions
   field. Seal the input alongside other preparation artifacts and bind its hash
   into RunSpec. Omit the optional digest for ordinary runs so their serialization
   and approval semantics stay unchanged. Revalidate on launch.
3. Reuse the existing driver and verification phase. After fresh human approval,
   record imported step evidence explicitly and skip the implementation model
   phase. Supply identical frozen report text to both verifier variants. Preserve
   command receipt checks, sandbox, tools and shutdown. Rejection/edit/amendment
   stops a verifier-only trial instead of silently invoking planner/executor;
   revised trials require fresh preparations and decisions.
4. Add focused integration coverage for zero calls before approval, exactly one
   verification phase after approval, imported-step provenance, frozen-input
   tampering, and no automatic planning on amendment. Cover bounded input validation
   and ordinary preparation/driver regressions. No full workspace suite.
5. Package a new versioned binary. Freeze the original verifier pilot's externally
   passing three-file candidate in a new clean deterministic commit, preserving
   the original task and canonical plan bytes. Record its source phase and patch
   hashes. Create ten independent identical checkouts and imported-plan preparations
   (zero model calls), five per verifier. Freeze all controls and validate full
   RunSpecs and phase prompts. Retain the same model/provider/settings and renderer.
6. Publish the complete plan, ten exact targets, pinned batch input, source/control
   inventory and progress ledger. Stop for the human decisions before execution.
   After approval use jobs=2, alternate condition order by replicate and report
   completion, report validity, costs, timing and changed/temporary files per trial.

## Architecture critique

No upstream core, model provider, TUI, sandbox or subagent lifecycle changes.
All runtime edits are in fork-owned lab crates. The sensitive local seams are
the driver and sealed-input loader: keep normal behavior intact and isolate input
validation in its own module. A RunSpec digest field is needed so identical plan
hashes cannot hide changed candidate evidence. It is preferable to encoding mode
switches in task prose or inventing an executor that emits synthetic success.

Do not add generic phase graphs, resumption, an evaluator scheduler or a new
comparison framework. Keep the imported candidate immutable as experimental input;
each verifier still has the existing workspace-write permissions in its own clone
so any candidate edits/temporary files are observable outcomes. Do not change the
verifier instructions again in this experiment. Source phase evidence is archived
and independently checked during setup; imported progress is explicitly labelled
and never counted as a new executor call. The original failed workflow's passing
candidate is eligible because candidate correctness and workflow completion differ.

Five observations per variant remain exploratory. Model serving revision and
provider queueing are unknown. Do not infer general reliability or billable spend
from this sample. Approval applies only to the exact newly reviewed trial targets;
there are no retries or amendment approvals in this preparation scope.
