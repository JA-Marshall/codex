# From a loose idea to usable kickoff prompts

Start with the conversation. There is no form to complete before discussing the idea. When the direction is clear enough, ask Codex:

> Turn this discussion into the smallest useful roadmap. Preserve my original intent and acceptance examples. Detail the next demonstrable outcome; keep later work broad. Split only where outcomes can be verified independently or a discovery could change the next step. Record consequential unanswered questions, assumptions and exclusions. Produce portable kickoff prompts so I can launch one in a fresh Codex thread. Do not implement yet.

For a roadmap that can be revised without losing obligations, have Codex save the source intent and a proposal using the shape in `experiments/workflows/our_v0.py:PLAN_SCHEMA`, then run:

```sh
python lab/experiments/roadmap.py --intent work/idea/intent.txt \
  --proposal work/idea/proposal.json --output work/idea/kickoffs-v1
```

Codex writes the proposal; you inspect the resulting outcome and prompts. Each prompt includes the original intent, source requirement IDs, acceptance examples, prerequisites, repository evidence, decision boundary and questions. Paste the next ready prompt into a fresh coding thread. Keep an increment small enough to demonstrate and review as one useful change. A research spike can be an increment when its outcome is evidence needed for the next decision.

After trying the result, describe what you learned. To revise remaining work, ask Codex to retain completed increment records and original requirements, write an updated proposal and a short discovery note, and export a new directory:

```sh
python lab/experiments/roadmap.py --intent work/idea/intent.txt \
  --proposal work/idea/proposal-v2.json --previous work/idea/kickoffs-v1/roadmap.json \
  --discovery work/idea/discovery.txt --completed first-increment \
  --output work/idea/kickoffs-v2
```

An explicit new request from you can be supplied with `--owner-followup path/to/request.txt`. It adds separately sourced obligations; an agent's discovery cannot authorize new scope. Original acceptance and completed work remain in the record. Structural checks preserve provenance and coverage; they do not prove the proposal correctly interprets your intent.

The experimental `our-v0` benchmark adapter implements a read-only planner, a fresh builder for each increment, one independent reviewer per review pass, and at most two repairs across the entire project allowance. The host runs public checks; the final product is independently graded only after shutdown. Whole-task public checks are diagnostic for intermediate increments and required at the final increment. Reviewer findings must name an original obligation, concrete evidence, consequence and smallest fix; zero findings is valid. Later discoveries can revise remaining work within a bounded revision count.

The command above exports prompts; it does not silently launch threads or a campaign. The runtime adapter and human kickoff workflow are distinct interfaces. Benchmark quality or effort advantages remain experimental until measured.
