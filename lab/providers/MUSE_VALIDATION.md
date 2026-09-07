# Muse Contributor live validation — 2026-09-07

Direct `muse-spark-1.3-contributor` inference works through the existing Responses provider. The approved workflow smoke run **failed** its final evidence-reference check. Its implementation and Python byte assertion succeeded. These are separate results; no successful end-to-end workflow or benchmark score is claimed.

The executable used source commit `be9c9bee68a1b166d2cf79329d1373f7ad7b8fb4` on the pinned Codex baseline. All live inputs were a small synthetic fixture. The exact [catalog](muse-contributor.models.json), [routing template](muse.toml.example) and [validation observations](muse-validation-2026-09-07.json) are shareable. Credentials and detailed task-bearing traces remain local. The original failed run is preserved unchanged.

## What passed and what failed

| Check | Observed result |
| --- | --- |
| Contributor inference | Exact Contributor ID returned by direct probes; no Standard fallback |
| Responses streaming | HTTP 200, terminal completed event, usage and output received |
| High reasoning and automatic summaries | Accepted; encrypted reasoning returned and replayed |
| Function tools | Call arguments, paired results and subsequent response passed |
| Canonical plan | Strict JSON output and Rust domain validation passed for the direct probe |
| Freeform `apply_patch` | HTTP 400: `custom` tools unsupported; catalog disables the tool |
| Actual research/planning, first attempt | Failed domain validation: prose used as a verification-ID reference |
| Research/planning with clarified task | Reached human gate; deliberately aborted; repository unchanged. Plan also mistakenly listed pending approval as a blocker |
| Approved imported-plan implementation | Created exactly `hello` plus LF in `greeting.txt` |
| Verifier command | Real Python byte assertion completed with exit 0 |
| Verification report | Failed: report cited displayed chunk ID instead of command API call ID |

The canonical plan in the final run came from the separate direct probe and had no blockers. The user approved its exact displayed plan with “Go”; the host recorded the corresponding digest-bound approval before dispatch. This run skips research/planning and is not interchangeable with either earlier task condition.

The verifier's actual call ID was `call_01a07ab2366b7220a9281e32e2e7115a`; its tool output displayed `Chunk ID: 0d4079`. Muse put `0d4079` in `checks[].call_id`. `codex-rs/lab-runtime/src/reports.rs::verification_evidence` correctly rejected it because no host-observed command had that call ID. A passing command does not authorize substituting a corrected report after the fact.

Independent inspection confirmed six file bytes (`68656c6c6f0a`) and only the untracked `greeting.txt` Git change. Both phase artifacts contain upstream shutdown-complete events. Eight inference calls and eight tool admissions were observed across the two phase threads. Final cumulative phase usage sums to 19,821 input tokens and 2,412 output tokens, including 1,658 reasoning tokens; cached input is 13,606. These totals exclude earlier probes and planning attempts. Elapsed run time was 150.596 seconds, including 107.442 seconds awaiting human approval.

The host's final Git/metrics capture was not reached. Root metrics remain unavailable, and the workflow journal ends in `failed`. The separate observation receipt records the above checks without replacing that authority or pretending missing evaluator metrics are zero. A local observer diff is stored beside the run directory.

## Configuration versus measured support

The exact catalog SHA-256 is `2453f904dc5b08c8d9180d36f665ae105140e9b2ae4a5962d244d4253c2ca4ef`. It combines documented context settings with measured Responses support and deliberate lab restrictions. Text-only input, 95% context headroom, 8 KiB truncation, base instructions and disabled auxiliary capabilities are experimental settings. They are not a comprehensive Meta capability advertisement. Preserve them when changing only the plan representation.

The catalog uses `apply_patch_tool_type: null` and the existing `exec_command` function. The upstream patch type currently supports only freeform, so inventing a function variant or translating the protocol would add unnecessary maintenance. No Muse-specific core changes were made.

The provider reports no immutable serving revision. Maximum output behavior, context pressure/compaction, broader task reliability and billing status remain unverified. Model release naming and the metadata's `created: 0` do not establish unchanged serving weights.

## Bounded follow-up proposal — not implemented

Historical proposal below: the user subsequently approved this follow-up with “Go”. The correction and its current validation status are tracked in [MUSE_INTERFACE_FIX_PLAN.md](../MUSE_INTERFACE_FIX_PLAN.md) and the progress ledger. This report continues to describe the original failed baseline.

1. Clarify canonical-domain constraints in the planner interface: step reference arrays contain IDs, verification commands belong in criterion descriptions, and awaiting the mandatory human gate is not a blocker. The relevant seams are `lab-runtime/src/driver.rs` plan prompt and `reports.rs::plan_schema`. Keep renderer-specific wording out of this contract. If procedural skills change, add a versioned module and explicitly selected configuration; retain the tested v1 hashes.
2. Make command references reliably available to the verifier. Inspect the existing tool-result/extension context surfaces before choosing a bounded host-issued receipt containing command call ID, status and criterion mapping. Keep the authoritative `ExecCommandEnd` join in `reports.rs`; do not accept chunk IDs, arbitrary model claims or the last successful command as replacements. Provider-assigned IDs may not be visible in generated model text, so prompt wording alone is not yet established as a sufficient fix.
3. Add focused integration coverage with different chunk/call IDs and the actual domain-reference failure. Replay the synthetic task under explicitly recorded changed instructions/context, then require fresh human approval for its new exact run target. Retain this failed baseline for comparison.

This proposal should stay within new lab modules and existing extension APIs. It does not justify modifying the central Codex loop, provider transport, shell executor, TUI or sandbox. A verification receipt changes model-visible context and therefore the experimental condition: record its bytes/version and hold it constant across renderers. Avoid building a generic policy bus, auto-repair loop or benchmark runner to solve these two observed interface gaps. Concrete implementation and any necessary amendment approval belong to a subsequent scoped plan.

## Local evidence and handoff

Under `/home/james/.cache/codex-lab-muse-validation`:

- `20260907T065440Z`: initial inference request, SSE and summary.
- `20260907T065748Z-contract`: function/reasoning/schema probes and custom-tool rejection.
- `20260907T070006Z-runtime`: first planner failure and separate offline domain validation.
- `20260907T070315Z-runtime`: clarified planner gate-refusal test, traces and final imported-plan run at `runs/muse-contributor-end-to-end`.

The last parent also contains `validation-observations.json` and `observed-final.diff`. `evidence/phase-01.json` and `phase-02.json` within the final run contain the real command events and final reports. No live host session or pending task-plan approval remains. Preserve these artifacts; the executable has no crash-resume path.
