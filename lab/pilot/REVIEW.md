# CSV pilot: human review pending

The Muse Contributor planning run has exited cleanly. Its original run remains `awaiting_plan_approval`. Neither experimental implementation has started.

The unchanged canonical review copy is [csv-plan-v1.json](csv-plan-v1.json), with its actual Markdown projection in [CSV_PLAN.md](CSV_PLAN.md). The authoritative source is the sealed run at `/home/james/.cache/codex-lab-csv-pilot/20260907T112052Z/runs/csv-md-prepared`. Both prepared conditions contain exactly the same canonical bytes.

- Plan: `task-plan`, revision 1.
- Canonical SHA-256: `f5e7683f1d510e50f0ea02ffb126d77374bdef53a08a6e6595ed023fd540c529`.
- Expected fresh execution targets: [approval-targets.json](approval-targets.json). These are review data, not saved permission or restored authority.
- Requested model: `muse-spark-1.3-contributor`; immutable serving revision remains unknown.
- Fixture baseline: `55fb025d812a1edff454d2f5c8cd90fdedc717e9`.

The plan proposes replacing the parser, hardening CLI output/error handling, adding regression tests, and verifying API/CLI behavior. Both representations fit the existing context budget.

Review concerns to resolve before approval:

1. S1 proposes a CSV reader "over text split". It should clarify preservation of embedded newlines in quoted fields, including CRLF, rather than accidentally discarding or normalizing category text.
2. Acceptance criteria require rejecting malformed/stray quotes, but the implementation step does not explain that validation beyond strict CSV parsing. The count-validation description should also make clear that every character must be an ASCII digit, including quoted counts with trailing newline characters.
3. S2 should explicitly preserve file newline bytes and produce exactly one final newline; its proposed combination of a newline-bearing string and `print` is ambiguous.

Recommendation: request a plan amendment clarifying these points. If the human chooses to run the plan as written, retain these concerns and let any actual amendment/deviation affect the reported comparison classification. Do not silently rewrite the canonical plan or count host-generated feedback as a human decision.

Preparation cost belongs to its own run: two phase threads, 20,768 input tokens and 4,183 output tokens, 68,977 ms. JSON preparation reused the same plan and made no planner/model calls. The two prospective execution runs each require an explicit human decision bound to their own displayed target. The development approval does not grant either decision.
