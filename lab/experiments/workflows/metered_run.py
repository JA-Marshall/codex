"""One finite run: shared proxy admission, SDK session, workers, and cleanup."""

import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from provider_proxy import Journal, Proxy
from workflows.callbacks import UserInput
from workflows.sdk_session import SdkSession
from workflows.usage import UsageLedger
from workflows.workers import WorkerBridge, WORKER_TOOLS


class MeteredRun:
    def __init__(
        self,
        *,
        run_id,
        pin,
        workspace,
        artifacts,
        model,
        budget,
        shared_upstream,
        upstream_key,
        limiter,
        sandbox=None,
        allow_workers=True,
        reasoning_effort="medium",
        model_catalog=None,
        interaction_policy=None,
        owner_facts=(),
        owner_state=None,
        clock=None,
    ):
        # All live traffic must go through the existing shared service; this
        # relay cannot be configured as another independent provider allowance.
        endpoint = urlsplit(shared_upstream)
        if endpoint.scheme != "http" or endpoint.hostname not in (
            "localhost",
            "127.0.0.1",
        ):
            raise ValueError("use the loopback shared provider proxy")
        self.artifacts = Path(artifacts).resolve()
        workspace = Path(workspace).resolve()
        if self.artifacts.is_relative_to(workspace) or workspace.is_relative_to(
            self.artifacts
        ):
            raise ValueError(
                "candidate and host artifacts must be separate directories"
            )
        self.artifacts.mkdir(parents=True, exist_ok=False)
        self.journal = Journal(self.artifacts / "usage.jsonl")
        self.proxy_journal = Journal(self.artifacts / "proxy.jsonl")
        self.clock = clock
        self.clock_final = True
        self.ledger = UsageLedger(run_id, model, budget, self.journal, clock=clock)
        self.key = secrets.token_hex(32)
        self.proxy = Proxy(
            0,
            shared_upstream,
            upstream_key,
            limiter,
            self.proxy_journal,
            observer=self.ledger,
            client_key=self.key,
        )
        self.server_thread = threading.Thread(
            target=self.proxy.serve_forever, daemon=True
        )
        self.session = SdkSession(
            pin=pin,
            workspace=workspace,
            artifacts=self.artifacts / "session",
            model=model,
            provider="study",
            endpoint=self._endpoint,
            seconds=budget.seconds,
            sandbox=sandbox,
            reasoning_effort=reasoning_effort,
            model_catalog=model_catalog,
            clock=clock,
        )
        self.bridge = WorkerBridge(
            self.session, declare_group=self.ledger.declare_group
        )
        self.interactions = UserInput(self.session.cancelled)
        self.human_review = None
        self.interaction_policy = owner_state
        if owner_state is not None and owner_state.mode != interaction_policy:
            raise ValueError("project owner policy differs from frozen runtime")
        if interaction_policy is not None and owner_state is None:
            from workflows.interaction_policy import InteractionPolicy

            self.interaction_policy = InteractionPolicy(
                interaction_policy, self.session.journal, owner_facts
            )
        self.session.callback = self._callback
        self.finished = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.result = None
        self.allow_workers = allow_workers

    def _endpoint(self, worker_id):
        if worker_id not in self.ledger.workers:
            self.ledger.register(worker_id)
        return {
            "url": f"http://127.0.0.1:{self.proxy.server_port}/v1",
            "headers": {
                "Authorization": "Bearer " + self.key,
                "X-Lab-Worker": worker_id,
            },
        }

    def _callback(self, method, params):
        if method == "item/tool/requestUserInput":
            if len(json.dumps(params).encode()) > 16384:
                raise ValueError("user question exceeds limit")
            identity = {
                key: params.get(key) for key in ("threadId", "turnId", "itemId")
            }
            self.session.fidelity.record(
                "question_received", **identity, questions=params.get("questions")
            )
            try:
                response = (self.human_review or self.interaction_policy or self.interactions).ask(params)
            except Exception as error:
                self.session.fidelity.record(
                    "question_failed", **identity, error_type=type(error).__name__
                )
                raise
            self.session.fidelity.record(
                "question_answered", **identity, response=response
            )
            return response
        return self.bridge.callback(method, params)

    def _monitor(self):
        while not self.finished.wait(0.05):
            if (
                time.monotonic() >= self.ledger.deadline
                or self.session.cancelled.is_set()
            ):
                self.ledger.stop("deadline_or_session_cancelled")
            if self.ledger.stopped.is_set():
                self.session.cancelled.set()

    def start(self):
        if self.clock and self.clock.state in ("setup", "grading"):
            self.clock.transition("agent")
        self.server_thread.start()
        self.monitor.start()
        try:
            self.session.start()
            return self
        except BaseException:
            self.close()
            raise

    def parent(self, prompt):
        if self.bridge.parent_thread is None:
            self.session.new_thread(
                "parent",
                tools=WORKER_TOOLS if self.allow_workers else [],
                writable=True,
            )
            self.bridge.parent_thread = self.session.threads["parent"]
        return self.session.turn("parent", prompt)

    def close(self):
        if self.result is not None:
            return self.result
        self.ledger.stop("run_closing")
        self.session.cancelled.set()
        receipt = self.session.close()
        self.bridge.close()
        if self.server_thread.is_alive():
            self.proxy.shutdown()
        self.proxy.server_close()
        handlers_stopped = self.proxy.wait_for_idle(5)
        self.finished.set()
        if self.monitor.ident is not None:
            self.monitor.join(timeout=1)
        if self.server_thread.ident is not None:
            self.server_thread.join(timeout=1)
        if self.clock and self.clock.state != "terminal":
            try:
                self.clock.transition("terminal" if self.clock_final else "grading")
            except RuntimeError:
                pass
        result = {
            "interactions": self.interaction_policy.snapshot()
            if self.interaction_policy
            else {"policy": "human-required"},
            "fidelity": self.session.fidelity.snapshot(),
            "process": receipt,
            "usage": self.ledger.snapshot(),
            "provider_handlers_stopped": handlers_stopped,
        }
        (self.artifacts / "runtime-result.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        # Do not close journal handles while an unconfirmed HTTP handler can
        # still append the eventual unknown-usage receipt.
        if handlers_stopped:
            self.journal.stream.close()
            self.proxy_journal.stream.close()
        self.result = result
        return result
