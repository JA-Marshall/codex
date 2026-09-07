# Muse interface validation — 2026-09-07

The corrected lab runtime completed an explicitly approved Muse Contributor implementation and verification on the synthetic greeting task. Muse created `greeting.txt` containing exactly `hello` plus one LF; the planned Python byte assertion passed, the verification report referenced the actual completed command, and the workflow journal reached `completed` with process exit 0.

This follows the preserved [failed baseline](MUSE_VALIDATION.md). Correction `3701f17` clarifies canonical ID references and exposes a bounded, verifier-only command receipt through existing extension interfaces. It leaves the final evidence join authoritative and adds no upstream core or provider changes. The [correction plan](../MUSE_INTERFACE_FIX_PLAN.md) records its design and tests.

## Approval and run boundary

Fresh run `muse-interface-v2` completed research/planning using the original task bytes, repository commit, Contributor catalog and deterministic role instructions. Its plan had valid criterion references and no blockers. The host then ended while waiting for human approval, before receiving the user's “Yes”; no implementation occurred. Its original journal remains at `awaiting_plan_approval`, with no live process or recorded approval.

After explaining the interruption, a replacement host imported the exact reviewed canonical plan. The canonical plan and effective run specification were verified byte-identical before the current human decision was submitted to the replacement's exact target. Only the run identity changed. Run `muse-interface-v2-approved-replacement` then completed implementation and verification. Both phase threads shut down, and every tool admission followed the host's approval event.

| Control | Recorded value |
| --- | --- |
| Model requested in every execution inference | `muse-spark-1.3-contributor` |
| Provider | `https://api.meta.ai/v1`, Responses |
| Repository commit | `8d8ecdeda687b8eb5800e0ba211f70a8e50e77fa` |
| Plan | `task-plan`, revision 1 |
| Plan SHA-256 | `3731daecdcd89aca353160d44dffd6b0c07464995a7e07cb3df29047bc4a360f` |
| Run-spec SHA-256 | `aa788f6a846dd7be00441455ba55f71eed66adb406a61cf186ff7566953c95d0` |

This was a replacement execution of the reviewed plan, not crash resume or an uninterrupted four-phase run. New tasks still require their own human approval.

## Verification and measurements

The verifier's receipt and final report both identify command `call_01a07aed647d7060a7f9af6c31231ebe`. Its recorded command is the planned Python byte check, with exit code 0 and stdout `ok 6`. Independent inspection confirmed file hex `68656c6c6f0a`, unchanged baseline HEAD, and only the new `greeting.txt` in Git status. Final diff size is 139 bytes.

| Measurement | Successful replacement only |
| --- | ---: |
| Phase turns | 2 |
| Inference calls observed in traces | 9 |
| Tool admissions | 8 |
| Input tokens | 25,971 |
| Cached input tokens, included above | 18,839 |
| Output tokens | 2,413 |
| Reasoning tokens, included in output | 1,563 |
| Host wall time | 80,805 ms |
| Human plan edits / amendments | 0 / 0 |
| Files changed | 1 |

These measurements exclude the preceding research/planning and interrupted approval wait. The replacement imported its plan and has zero planner phases. Original host metrics keep unavailable evaluator success, hidden-test success, deviation and aggregate call fields null; separate observations count trace calls without rewriting those metrics.

The correction passed **106/106** focused tests, with no skips, through `just test -p codex-lab-runtime -p codex-lab`. Scoped fix, formatting, strict all-target Clippy and binary build also passed. Tests were not repeated after final fix/format, following repository instructions. This results update changes documentation only.

## Evidence and limits

[Machine-readable observations](muse-interface-validation-2026-09-07.json) retain approval identity, binary/catalog hashes, command attribution, metrics and artifact hashes. Original journals, phase inputs/results, traces, final diff and operator recovery record remain local beneath `/home/james/.cache/codex-lab-muse-validation/20260907T074240Z-interface-v2`. The [progress ledger](../PROGRESS.md) records exact paths and completed session status.

The runtime trace retains the requested Contributor ID but its response projection does not retain the provider's reported model field; earlier direct API probes verified that field. Immutable serving version, hidden tests, general task reliability, maximum output behavior and context-pressure/compaction behavior remain unverified. This single task confirms the corrected interface works; it does not estimate benchmark success rates or isolate representation effects against the earlier runtime contract.
