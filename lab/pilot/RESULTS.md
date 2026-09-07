# CSV pilot results — 2026-09-07

Both exact execution targets were approved by the user as written and executed sequentially with `muse-spark-1.3-contributor`. The Markdown workflow failed its verifier-report contract. The JSON workflow completed, but independent evaluation found a CLI correctness failure. Neither outcome establishes a preferred renderer.

| Observation | Markdown | JSON |
| --- | --- | --- |
| Workflow terminal state | failed | completed |
| Independent API cases | not evaluated | 21/21 |
| Independent CLI cases | not evaluated | 20/21 |
| Fixed public tests | not evaluated | 3/3 |
| Independent task success | unknown | false |
| First plan approved | yes | yes |
| Human edits / amendments | 0 / 0 | 0 / 0 |
| Phase turns / inference calls | 2 / 32 | 2 / 31 |
| Tool admissions | 36 | 35 |
| Input / output tokens | 361,599 / 18,023 | 387,792 / 21,275 |
| Cached input tokens | 326,206 | 348,621 |
| Time through terminal workflow event | 250.286 s | 299.588 s |
| Changed files / diff bytes | 3 / 9,038 | 3 / 9,469 |

Execution costs exclude preparation: the shared plan required two research/planning phases, 20,768 input and 4,183 output tokens, and 68.977 seconds. JSON preparation imported those exact canonical bytes without model calls. JSON's complete host duration, including final evidence capture after the terminal workflow event, was 311.579 seconds. Markdown failed before final host metrics/diff capture; its table entries are separate diagnostic observations recovered from retained phase traces and the quiescent checkout. Plan deviations were not independently scored and remain unknown.

## What happened

Markdown's verifier submitted three check records for two planned verification IDs: V1 once and V2 twice, splitting the valid and invalid CLI observations. The host rejected this with `every planned verification requires one observation` and recorded terminal state `failed`. Both phase threads shut down. The strict completion/evidence checks were retained. The current live evaluator requires a completed workflow and refused this failed run before producing results; no hidden-test success is claimed for Markdown.

JSON submitted one check record for each verification ID and completed. The independent evaluator's isolation probes passed, then its fixed cases exposed a quoted-category CRLF bug. `Path.read_text(encoding="utf-8")` normalized the embedded CRLF to LF before parsing. The API preserved the category when given the original string; the CLI emitted `two\nlines` instead of `two\r\nlines`. All other independent API/CLI cases and the three fixed public tests passed. Host completion therefore did not imply task success.

The original review explicitly identified newline preservation as a concern. The user approved the plan as written; neither candidate was manually repaired, neither run requested an amendment, and no failing journal was rewritten or retried as a success.

## Evidence and controls

- Human authorization: [execution-approval.json](execution-approval.json). [REVIEW.md](REVIEW.md) and [approval-targets.json](approval-targets.json) preserve the earlier pending-review snapshot.
- Results and artifact fingerprints: [results-2026-09-07.json](results-2026-09-07.json).
- Unmodified comparison output: [comparison-2026-09-07.json](comparison-2026-09-07.json).
- Unmodified JSON evaluator output: [json-evaluation-2026-09-07.json](json-evaluation-2026-09-07.json).

The comparison is `descriptive_only`: Markdown lacks completed-workflow metrics, final host Git evidence and independent evaluation. Among the other recorded controls, only `plan.renderer` differs. Both executions used canonical plan SHA-256 `f5e7683f1d510e50f0ea02ffb126d77374bdef53a08a6e6595ed023fd540c529`, fixture commit `55fb025d812a1edff454d2f5c8cd90fdedc717e9`, the same runtime binary, provider settings and exact role instructions. Fresh displayed targets matched the approved run-specific fingerprints. Human approval preceded every admitted tool. Original preparation journals remain unapproved and unchanged.

Full local artifacts remain under `/home/james/.cache/codex-lab-csv-pilot/20260907T112052Z`: `runs/`, `traces/`, `comparison/`, and `observations/` (separate diagnostic diffs). Raw model traces and credentials are not published. Immutable remote serving revision and unrecorded provider/system state remain unknown. One sequential observation per condition supports no reliability estimate or causal winner.

## Concrete follow-up boundaries

1. Propose a separate verifier-contract change: support multiple observed commands per verification ID, or explicitly instruct a single aggregate assertion command. Preserve actual completed-command joins, uniqueness rules and failure handling; do not retroactively reinterpret this run.
2. Propose independent evaluation of terminal failed runs only after verified phase shutdown and acquiring the existing launch lock. Record workflow failure separately from candidate correctness and capture failure metrics/diffs without inventing completion.
3. Review a new shared plan that explicitly preserves newline bytes at the CLI boundary, then obtain fresh approvals for a new pair on clean baseline checkouts. Keep these pilot artifacts immutable.

These follow-ups are proposals, not additional implemented features. The approved N01–N04 foundation and live pilot attempt are finished. Focused foundation validation remains 83 passing runtime tests and two passing Python calibration tests, plus scoped lint/format/build checks; this results-only follow-up did not rerun Rust tests or the full workspace suite.
