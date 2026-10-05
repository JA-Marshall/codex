# Normal Codex use and the human comparison

The usable product workflow starts with conversation. Use `$idea-to-increments` to explore a larger idea, export a few reviewable kickoff prompts, implement the next ready increment, try it, and revise remaining work. Small edits can proceed directly. See [the kickoff guide](IDEA_TO_KICKOFFS.md) for checked exports and revisions. The skill source is [idea-to-increments](skills/idea-to-increments/SKILL.md).

Example first message:

> Use $idea-to-increments. I want to talk through this idea before deciding what to build. Help me find the smallest useful outcome, then give me prompts I can use to implement the first steps. Challenge assumptions that materially change what we should build.

The exported prompt can be pasted into a fresh normal Codex thread. This ordinary chat workflow is separate from the metered benchmark adapter. Human pauses, changes of mind and corrections must remain real interactions; a scripted owner oracle cannot supply evidence about user effort or preference.

## Six matched human pairs

Before starting, select six public development scenarios and record their starting revision, user intent, task-specific acceptance examples, budget/time allowance and model/effort. Use fresh isolated workspaces for both workflows. For three pairs try BMAD first, and for three try the lean workflow first; choose and record the order before running. Record learning/carryover from seeing the first result. These are exposed development scenarios, not sealed confirmation.

A practical six-pair set covers archive/restore, CSV review, atomic stock changes, a retention decision that needs the owner, a checkout feature with a later change, and reservation/cancellation integration. The human supplies consequential choices; record the answer and reuse the same authorized facts for the matched second workflow. Do not expose protected graders or hidden cases to either agent.

For BMAD, use the pinned stock interactive entry and retain its actual questions, checkpoints and user decisions. Do not replace those checkpoints with delegated unattended answers and label them interactive. For the lean workflow, explore the idea, inspect its proposed increments, choose the next ready increment, try the output, and supply a concrete discovery or follow-up. Preserve the initial intent and completed work in the revised roadmap.

For each arm record:

- Start/end times and active human minutes, separating waiting time.
- Questions asked, answers supplied, corrections, review minutes and interventions.
- The initial intent, exported prompts/spec, implementation diff, check results, runnable artifact and the actual revision after trying it.
- Human ratings with examples: meets my intended outcome (0 absent, 1 partial, 2 meets); I can judge the next step (0 unclear, 1 needs explanation, 2 clear); unnecessary process (0 none, 1 noticeable, 2 obstructive).
- Which result the human would keep, including neither/tie, and the reason. Preference and executable correctness are separate observations.

Stop a scenario at its predeclared allowance and retain incomplete outcomes. Do not repair one arm after seeing the other's private score. A changed scenario becomes a new named pair, with the original attempt retained. Six pairs give usability evidence for this participant and these scenarios; they cannot establish a general winner. Confirmation rubrics requiring two independent human ratings/adjudication remain a separate P11 dependency.

Status: protocol prepared; no human pairs have been completed or preferences inferred. The validator/coordinator must collect actual participation before reporting P10 complete.
