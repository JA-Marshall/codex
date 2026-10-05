"""Native direct question to durable broker, verified pause and exact continuation."""

import threading
import time
import uuid

from workflows.human_pause import HumanPause
from workflows.review_projection import project_question
from workflows.review_ownership import host_identity


class HumanReview:
    def __init__(self, run, client, *, trial, block, scenario, title, original_request):
        self.run, self.client = run, client
        self.trial, self.block, self.scenario = trial, block, scenario
        self.title, self.original_request = title, original_request
        self.generation = uuid.uuid4().hex
        self.pause = HumanPause(run)
        self.revision = 0
        self.guard = threading.Lock()
        self.decisions = []
        self.waiting_dispatch = None
        self.registered = False
        self.errors = []
        self.pending_ack = None
        self.original_dispatch = getattr(run.ledger, "on_dispatch", None)
        run.ledger.on_dispatch = self.observed_dispatch

    def observed_dispatch(self, worker, request):
        if self.original_dispatch:
            self.original_dispatch(worker, request)
        waiting = self.waiting_dispatch
        if waiting and worker == waiting[0]:
            waiting[1]["request"] = request
            waiting[2].set()

    def _retry(self, operation, **payload):
        while not self.run.session.cancelled.is_set():
            try:
                result = self.client.call(operation, **payload)
                if self.run.clock.state == "outage":
                    self.run.clock.transition("human_wait")
                return result
            except OSError:
                if self.pause.boundary:
                    self.pause.verify()
                    if self.run.clock.state == "human_wait":
                        self.run.clock.transition("outage")
                if self.run.clock.snapshot()["interruption"]:
                    raise RuntimeError("trial interrupted during broker outage")
                time.sleep(0.2)
        raise RuntimeError("trial cancelled")

    def ask(self, params):
        with self.guard:
            if self.pending_ack and not self.pending_ack.wait(5):
                raise RuntimeError("previous continuation remains uncertain")
            self.revision += 1
            if not self.registered:
                self._retry("register", trial=self.trial, block=self.block, scenario=self.scenario,
                            generation=self.generation, identity=host_identity(self.run.session.process.identity), title=self.title)
                self.registered = True
            checkpoint_id = uuid.uuid4().hex
            presented = project_question(params, request=self.original_request, decisions=self.decisions)
            request = self._retry("publish", trial=self.trial, generation=self.generation,
                                 revision=self.revision, kind="clarification", raw=params,
                                 presented=presented, checkpoint_id=checkpoint_id)
            identity = dict(request=request, trial=self.trial, generation=self.generation, revision=self.revision)
            pausing=False
            try:
                self._retry("transition", **identity, state="pausing")
                pausing=True
                boundary = self.pause.pause(kind="tool_callback")
                self._retry("transition", **identity, state="pending", evidence=boundary)
                while True:
                    self.pause.verify()
                    status = self._retry("status", **identity)
                    state = status["state"]
                    if state == "answered":
                        self.run.clock.response_committed(status["answered_at"])
                        break
                    if state != "pending":
                        raise RuntimeError("checkpoint no longer awaits a response")
                    if self.run.session.cancelled.wait(0.2):
                        raise RuntimeError("trial cancelled")
                # Consumption intentionally is not retried: a lost receipt here
                # is uncertain execution and cannot authorize a second apply.
                answer = self.client.call("consume", **identity)
                response = answer["answers"] if answer["action"] == "answer" else {
                    q["id"]: ["I cannot decide." + (" " + answer["text"] if answer["text"] else "")]
                    for q in params["questions"]}
                self.decisions.extend(text for values in response.values() for text in values)
                worker = next(worker for worker, thread in self.run.session.threads.items() if thread == params["threadId"])
                observed, details = threading.Event(), {}
                self.waiting_dispatch = (worker, details, observed)
                self.pending_ack = threading.Event()
                threading.Thread(target=self._ack, args=(identity, observed, details, self.pending_ack), daemon=True).start()
                self.pause.resume()
                return {"answers": {key: {"answers": values} for key, values in response.items()}}
            except BaseException as error:
                self.pause.interrupt()
                try:
                    self.client.call("interrupt", trial=self.trial, generation=self.generation, reason=type(error).__name__,status='pause_failed' if pausing and self.pause.boundary is None else 'interrupted')
                except Exception:
                    self.errors.append("broker interruption acknowledgement unavailable")
                raise

    def _ack(self, identity, observed, details, done):
        try:
            while not observed.wait(0.05):
                if self.run.session.cancelled.is_set():
                    raise RuntimeError("consumed response has no observed continuation")
            self._retry("continued", **identity, evidence={"provider_request": details["request"]})
            done.set()
        except Exception as error:
            self.errors.append(type(error).__name__)
