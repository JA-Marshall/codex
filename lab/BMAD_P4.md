# P4: stock BMAD transport and independently graded SDK trials

BMAD v6.12.0 is pinned in `bmad-method.lock.json`. Provisioning uses the stock
installer and renderer, preserves the license, and records every installed asset.
The installed `_bmad` and `.agents` trees are immutable during execution;
`_bmad-output` holds bounded text artifacts. Only those reserved namespaces are
added to local Git excludes. Disposable repositories permit local commits.

The outer filesystem boundary uses the pinned binary's bundled bubblewrap and
records its exact arguments and resource hashes. Private task files and host
artifacts are absent. Nested Codex command sandboxes enforce writer/reviewer
permissions. Repository config, hooks, info, and object-info are immutable while
index, objects and refs remain writable for local commits. PID namespace teardown
and HTTP-handler shutdown must be confirmed before candidate capture.

`candidate.py` inventories final product bytes against the original starter,
including committed and ignored files. Protected assets are verified separately.
Control artifacts are retained in evidence but absent from the grading copy, so
they cannot provide hidden runtime dependencies. The existing `evaluate_task.grade`
runs public and private acceptance checks. Product byte limits are shared across
SDK arms. Reporting failure, independent acceptance and evaluator failure remain
separate; evaluator failures retain null acceptance and a failure receipt.

`BmadDispatch` invokes stock Build Auto or interactive Build through the Codex
worker transport. Review policy stays in stock BMAD. Explicitly selected spec
statuses are claims. Other discovered claims are retained without guessing an
authoritative spec or inferring stock completion from an ended model turn.
Planning continuation preserves the same thread, deadline and aggregate budget.
This is in-process continuation, not durable restart/resume. A blocked spec needs
owner resolution; a completed spec starts a separate follow-up review invocation.

`run_campaign.py --sdk-config <settings.json> --prepare-only ...` extends the
existing freezer and scheduler. `sdk-workflows.toml` names the direct single-session
control and BMAD transport arm. The direct arm has no worker tools. The archive
pins the local SDK, its Python dependencies, runtime binary, explicit model/effort,
optional model catalog, stock BMAD and installed Node dependencies, and the shared
provider service. No published CLI wheel replaces the local binary. The recorded
token ceiling is conservative admission with output limits, not an exact provider
tokenization guarantee. There are no automatic retries or durable resume yet.

Offline integration coverage includes stock install/render inside the actual
sandbox; direct, proc-root and symlink private-read denial; reviewer-write denial;
real local commits followed by private grading; planning continuation; ignored
scope violations; a falsely claimed successful product; a reporting exception
with correct product; a grader exception; and the actual archived `--trial`
subprocess using plain pinned Python and a local mock provider service.

These scripted probes establish execution and evaluation mechanisms. They do not
establish autonomous BMAD policy fidelity, Muse capability, or comparative quality.
Those remain gates for the frozen four-run compatibility study. P5–P11 and the
actual human usability study are not completed by this implementation checkpoint.

Compatibility evidence additionally retains exact turn prompts, group membership,
and command intents in a bounded 16 MiB journal. Full provider streams and command
output are not copied. A truncation flag makes fidelity unauditable; it cannot be
treated as proof of stock workflow compliance.

The first executed compatibility attempt (v2) hit a sandbox startup error in all
four slots and made zero model requests. Those results remain preserved as
infrastructure failures. Production `/home` layouts now receive a private `/tmp`
mount for nested bubblewrap staging, with both path layouts covered offline.
SDK aggregate reports distinguish known-zero usage, unknown usage, and a model
turn ending without an authoritative BMAD completion claim.
