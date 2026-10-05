"""Host-only observable change delivery from independently graded snapshots."""

import hashlib
import re

from task_registry import inventory, relative_path
from task_v2 import TaskSpecV2


class Milestones:
    def __init__(self, task, journal):
        self.task, self.journal = task, journal
        self.spec = TaskSpecV2.load(task.root, task.manifest)
        self.assets = inventory(task.root)
        self.delivered = []

    def advance(self, evaluated):
        if inventory(self.task.root) != self.assets:
            raise ValueError("milestone assets changed")
        if len(self.delivered) == len(self.spec.changes):
            return None
        change = self.spec.changes[len(self.delivered)]
        milestone = next(
            item for item in self.spec.milestones if item["id"] == change["after"]
        )
        digest = evaluated.get("candidate_sha256")
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("milestone requires identified product snapshot")
        by_case = {}
        for check in evaluated["checks"]:
            if type(check.get("passed")) is not bool:
                raise ValueError("unknown milestone evaluator evidence")
            by_case.setdefault(check["case"], []).append(check["passed"])
        states = {
            name: all(by_case[name]) if name in by_case else None
            for name in milestone["cases"]
        }
        reached = (
            evaluated.get("scope_success") is True
            and evaluated.get("build_success") is True
            and evaluated.get("public_test_success") is True
            and all(value is True for value in states.values())
        )
        self.journal.event(
            "milestone_probe",
            milestone=milestone["id"],
            candidate_sha256=digest,
            predicates=states,
            reached=reached,
        )
        if not reached:
            return None
        path = relative_path(self.task.root, change["brief"])
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != self.assets[change["brief"]]:
            raise ValueError("change brief changed before delivery")
        brief = content.decode("utf-8")
        self.delivered.append(milestone["id"])
        self.journal.event(
            "change_delivered",
            milestone=milestone["id"],
            candidate_sha256=digest,
            brief_sha256=self.assets[change["brief"]],
        )
        return brief
