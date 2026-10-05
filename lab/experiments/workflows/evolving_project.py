"""Finite stop/probe/change increments with one conserved project allowance."""

from dataclasses import replace
import json
from pathlib import Path
import time

from provider_proxy import Journal
from workflows.interaction_policy import (
    AUTHORIZATION,
    DELEGATED_TASK,
    InteractionPolicy,
)
from workflows.milestones import Milestones


class EvolvingProject:
    def __init__(self, task, budget, artifacts, *, clock=None):
        if task.manifest.get("track") != "B":
            raise ValueError("evolving controller requires an explicitly evolving task")
        self.task, self.budget = task, budget
        self.artifacts = Path(artifacts)
        self.artifacts.mkdir(parents=True, exist_ok=False)
        self.journal = Journal(self.artifacts / "project.jsonl")
        self.milestones = Milestones(task, self.journal)
        self.owner = InteractionPolicy(
            DELEGATED_TASK, self.journal, self.milestones.spec.owner_facts
        )
        self.clock = clock
        self._deadline = time.monotonic() + budget.seconds
        self.runtimes, self.increments = [], []
        self.requests = self.charged_tokens = 0

    @property
    def deadline(self):
        return self.clock.deadline if self.clock else self._deadline

    @deadline.setter
    def deadline(self, value):
        if self.clock is not None:
            raise RuntimeError("human project deadline belongs to its shared clock")
        self._deadline = value

    def run(self, make_run, invoke, evaluate):
        """Callbacks are host code; evaluate must capture only confirmed-stopped bytes."""
        prompt = AUTHORIZATION + "\n\n" + (self.task.root / "TASK.md").read_text()
        briefs = []
        evaluated = terminal = runtime = current = None
        try:
            for index in range(len(self.milestones.spec.changes) + 1):
                seconds = (self.clock.limit-self.clock.snapshot()["agent_seconds"]
                           if self.clock else self.deadline-time.monotonic())
                requests = self.budget.requests - self.requests
                tokens = self.budget.tokens - self.charged_tokens
                if min(seconds, requests, tokens) <= 0:
                    self.journal.event("project_budget_exhausted", increment=index)
                    break
                remaining = replace(
                    self.budget, requests=requests, tokens=tokens, seconds=seconds
                )
                evaluated = terminal = runtime = None
                if self.clock and self.clock.state != "setup":
                    self.clock.transition("setup")
                current = make_run(index, remaining, self.owner)
                try:
                    if self.clock:
                        if not (current.clock is current.session.clock is current.ledger.clock is self.clock):
                            raise RuntimeError("project and runtime must share one human clock")
                        current.clock_final = False
                    else:
                        current.session.deadline = min(current.session.deadline, self.deadline)
                        current.ledger.deadline = min(current.ledger.deadline, self.deadline)
                    if time.monotonic() >= self.deadline:
                        raise TimeoutError("project deadline expired during setup")
                    current.start()
                    if time.monotonic() >= self.deadline:
                        raise TimeoutError(
                            "project deadline expired during runtime startup"
                        )
                    terminal = invoke(current, prompt)
                except Exception as error:
                    terminal = {
                        "status": "failed",
                        "error": {
                            "message": str(error)[:2048],
                            "error_type": type(error).__name__,
                        },
                    }
                    self.journal.event(
                        "increment_error",
                        increment=index,
                        error_type=type(error).__name__,
                        message=str(error)[:2048],
                    )
                finally:
                    runtime = current.close()
                    self.runtimes.append(runtime)
                usage = runtime["usage"]
                self.requests += usage["requests"]
                self.charged_tokens += usage["charged_tokens"]
                if (
                    runtime["process"]["stop_status"] != "confirmed"
                    or runtime["provider_handlers_stopped"] is not True
                ):
                    self.journal.event("project_stop_unconfirmed", increment=index)
                    break
                started = time.monotonic()
                evaluated = evaluate(current, list(self.milestones.delivered))
                record = {
                    "increment": index,
                    "candidate_sha256": evaluated["candidate_sha256"],
                    "task_success": evaluated["task_success"],
                    "terminal": None
                    if terminal is None
                    else {
                        key: terminal.get(key)
                        for key in (
                            "status",
                            "error",
                            "thread_id",
                            "turn_id",
                            "workflow_status",
                        )
                    },
                    "evaluation_seconds": time.monotonic() - started,
                    "runtime_artifacts": str(current.artifacts),
                }
                self.increments.append(record)
                self.journal.event("increment_evaluated", **record)
                if (
                    usage["unknown_requests"]
                    or usage["in_flight"]
                    or not terminal
                    or terminal["status"] != "completed"
                    or terminal.get("workflow_status", "completed") != "completed"
                ):
                    break
                brief = self.milestones.advance(evaluated)
                if brief is None:
                    break
                briefs.append(brief)
                known = [
                    fact["answer"]
                    for fact in self.milestones.spec.owner_facts
                    if fact["id"] in self.owner.snapshot()["asked_facts"]
                ]
                prompt = (
                    AUTHORIZATION
                    + "\n\nOriginal task:\n"
                    + (self.task.root / "TASK.md").read_text()
                    + "\n\nDelivered follow-up requests:\n"
                    + "\n\n".join(briefs)
                    + "\n\nPreviously established owner facts:\n"
                    + "\n".join(known)
                    + "\nContinue from your existing product. Preserve earlier obligations. This is a new follow-up invocation; retain prior spec artifacts and statuses."
                )
                if len(prompt.encode()) > 32768:
                    raise ValueError("evolving project context exceeds limit")
            result = {
                "increments": self.increments,
                "runtime_receipts": self.runtimes,
                "requests": self.requests,
                "charged_tokens": self.charged_tokens,
                "reached_milestones": list(self.milestones.delivered),
                "owner": self.owner.snapshot(),
                "evaluation": evaluated,
                "terminal": terminal,
                "admitted_increments": len(self.runtimes),
                "all_stopped": all(
                    item["process"]["stop_status"] == "confirmed"
                    and item["provider_handlers_stopped"] is True
                    for item in self.runtimes
                ),
            }
            (self.artifacts / "project-result.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            return result
        finally:
            if self.clock and self.clock.state != "terminal":
                try:
                    self.clock.transition("terminal")
                except RuntimeError:
                    pass
            self.journal.stream.close()
