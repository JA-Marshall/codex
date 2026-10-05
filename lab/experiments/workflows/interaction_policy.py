"""Explicit shared task authorization; product facts remain separately bounded."""

import json
import threading

from task_v2 import AuthorizedOwner


DELEGATED_TASK = "delegated-task-v1"
AUTHORIZATION = (
    "The operator has authorized this finite run to implement the request in TASK.md "
    "within the assigned role, permitted write paths, and existing run budget. "
    "Routine planning, implementation, local testing, and disposable local commits "
    "within that scope need no additional approval. This does not authorize scope "
    "expansion, deployment, external messages, or invented product requirements. "
    "Ask for missing product facts; if a required fact remains unspecified, report "
    "the ambiguity or block instead of treating this authorization as a product decision."
)


class InteractionPolicy:
    def __init__(self, mode, journal, facts=()):
        if mode != DELEGATED_TASK:
            raise ValueError("unsupported delegated interaction policy")
        self.mode = mode
        self.owner = AuthorizedOwner(
            facts,
            journal,
            unspecified="No additional product fact is specified. " + AUTHORIZATION,
        )
        self.lock = threading.Lock()

    def ask(self, params):
        # All children share one allowance. Authorization is conditional on the
        # frozen task, never a blanket selection of an agent's Approve option.
        with self.lock:
            response = self.owner.ask(params)
            if len(json.dumps(response).encode()) > 16384:
                raise ValueError("delegated response exceeds limit")
            return response

    def snapshot(self):
        with self.lock:
            return {"policy": self.mode, **self.owner.snapshot()}
