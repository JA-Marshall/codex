"""Verified pause boundary shared by tool-callback and completed-turn adapters."""

import threading
import time

from workflows.process_pause import ProcessPause


class HumanPause:
    def __init__(self, run):
        if run.clock is None or run.session.clock is not run.clock or run.ledger.clock is not run.clock:
            raise ValueError("all trial watchdogs must share one clock")
        self.run = run
        self.processes = ProcessPause(run.session.process)
        self.guard = threading.Lock()
        self.boundary = None

    def pause(self, *, kind):
        if kind not in ("tool_callback", "completed_turn"):
            raise ValueError("explicit checkpoint adapter required")
        with self.guard:
            if self.boundary is not None:
                raise RuntimeError("trial already has a human checkpoint")
            run = self.run
            run.clock.transition("pausing")
            deadline = time.monotonic() + 30
            run.ledger.pause_admission()
            run.session.work_admission.clear()
            try:
                if kind == "completed_turn" and run.session.active:
                    raise RuntimeError("completed-turn checkpoint has active turns")
                # Drain HTTP before freezing its reader: a full socket buffer
                # must not leave a provider stream held throughout human wait.
                if not run.proxy.wait_for_idle(max(0, deadline - time.monotonic())):
                    raise TimeoutError("provider stream did not drain")
                if run.ledger.snapshot()["in_flight"] or run.ledger.stopped.is_set():
                    raise RuntimeError("provider reconciliation failed")
                evidence = self.processes.freeze(deadline)
                if run.ledger.snapshot()["in_flight"]:
                    raise RuntimeError("model work appeared after admission closed")
                run.clock.transition("human_wait")
                self.boundary = dict(evidence, checkpoint_kind=kind, usage=run.ledger.snapshot())
                run.journal.event("human_pause_confirmed", **self.boundary)
                return self.boundary
            except BaseException:
                self.processes.terminate()
                run.ledger.stop("human_pause_failed")
                run.session.cancelled.set()
                run.journal.event("human_pause_failed", checkpoint_kind=kind)
                raise

    def verify(self):
        self.processes.verify()
        if self.run.clock.snapshot()["interruption"]:
            raise RuntimeError("trial clock interrupted")
        if self.run.ledger.snapshot()["in_flight"]:
            raise RuntimeError("model work during pause")

    def resume(self):
        with self.guard:
            self.verify()
            self.run.clock.transition("agent")
            self.run.ledger.resume_admission()
            self.processes.resume()
            self.run.session.work_admission.set()
            self.boundary = None
            # This only records release. Continuation needs a separate observed
            # runtime acknowledgement after the durable response is consumed.
            self.run.journal.event("human_pause_released")

    def interrupt(self):
        self.processes.terminate()
        self.run.ledger.stop("human_checkpoint_interrupted")
        self.run.session.cancelled.set()
