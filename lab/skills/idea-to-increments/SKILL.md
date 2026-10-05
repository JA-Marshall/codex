---
name: idea-to-increments
description: Explore a larger product idea, turn it into reviewable implementation prompts, or revise remaining work after trying a result. Use for workflow decomposition, not routine small edits.
---

Let the user explore in conversation. When enough is known to act, preserve their original intent and concrete examples. Detail the next useful outcome and leave later work broad. A step should end in something the user can try, or evidence that resolves a consequential uncertainty. Split at independent acceptance boundaries, risky assumptions, or discoveries that could change the next step; do not split by agent role alone.

Export a small set of kickoff prompts. Each includes its outcome, source requirements, acceptance examples, prerequisites, relevant repository evidence, consequential questions, and what is deferred. State assumptions as assumptions. Ask only about missing decisions that change the next action. Existing authorization still applies; exporting a roadmap does not itself launch new threads.

If this repository includes `lab/experiments/roadmap.py`, read `lab/IDEA_TO_KICKOFFS.md` and use that exporter for checked, revisionable artifacts. Otherwise save ordinary Markdown prompts in a task-appropriate location. Do not install benchmark infrastructure into the user's product to export prompts.

For implementation, start the next ready increment in a fresh context when the user asks. Preserve the original requirements in the handoff. Review the actual result against those requirements and meaningful checks. A finding needs evidence, consequence, and a small fix; an empty review is valid. Use parallel work only for independent outcomes with clear interfaces and explicit authorization.

After the user tries it, record what changed in their understanding. Revise the remaining steps while preserving completed work and original obligations. New scope must come from the user's request; an agent discovery alone cannot authorize it. Avoid promising that structural checks prove the plan matches the user's intent.
