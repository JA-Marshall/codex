"""One host-owned clock for human trials; automated conditions stay unchanged."""

import math
import threading
import time


class TrialClock:
    ACTIVE = frozenset(("agent", "pausing"))
    STATES = ACTIVE | {"setup", "human_wait", "outage", "handoff", "grading", "terminal"}

    def __init__(self, seconds, *, monotonic=time.monotonic, wall=time.time):
        if not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError("finite agent allowance required")
        self.limit = seconds
        self.monotonic, self.wall = monotonic, wall
        self.guard = threading.RLock()
        self.last_mono, self.last_wall = monotonic(), wall()
        self.created = self.last_wall
        self.state = "setup"
        self.elapsed = dict.fromkeys(self.STATES, 0.0)
        self.interruption = None
        self.ready_at = None
        self.segments = []
        self.segment_start = self.last_wall
        self.review_deadline_reached = False
        self.heartbeat_stop = threading.Event()
        self.heartbeat_thread = None
        if monotonic is time.monotonic and wall is time.time:
            self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.heartbeat_thread.start()

    def _heartbeat(self):
        while not self.heartbeat_stop.wait(0.2):
            with self.guard:
                self._tick()
                if self.state == "terminal":
                    return

    def _tick(self):
        if self.state == "terminal":
            return self.monotonic()
        mono, wall = self.monotonic(), self.wall()
        delta, wall_delta = mono - self.last_mono, wall - self.last_wall
        # A host heartbeat must run while a human waits. A long scheduling gap
        # is an outage requiring reconciliation, never credited as computation.
        if delta < 0 or abs(delta - wall_delta) > 2 or delta > 30:
            self.interruption = "clock_discontinuity_or_missing_heartbeat"
            self.state = "terminal"
        else:
            self.elapsed[self.state] += delta
        self.last_mono, self.last_wall = mono, wall
        if wall - self.created >= 7 * 86400:
            self.interruption = "trial_calendar_limit"
        self.review_deadline_reached = self.ready_at is not None and wall-self.ready_at >= 86400
        # A late poll cannot tell whether the service committed an on-time
        # answer. Only durable broker state can expire this particular review.
        return mono

    def transition(self, state):
        with self.guard:
            self._tick()
            if state not in self.STATES or self.state == "terminal" or self.interruption:
                raise RuntimeError("clock cannot transition")
            self._segment()
            if state == "human_wait" and self.ready_at is None:
                self.ready_at = self.last_wall
            elif state not in ("human_wait", "outage"):
                self.ready_at = None
            self.state = state
            if state == "terminal":
                self.heartbeat_stop.set()

    def _segment(self):
        if len(self.segments) >= 4096:
            self.interruption = "clock_event_limit"
            raise RuntimeError("clock event limit exceeded")
        self.segments.append((self.state, self.segment_start, self.last_wall))
        self.segment_start = self.last_wall

    def response_committed(self, at):
        with self.guard:
            self._tick()
            if self.ready_at is None or not self.ready_at <= at <= self.last_wall + 2:
                raise RuntimeError("response timestamp outside checkpoint interval")
            self._segment()
            # Service and runner use the same host wall clock. Reclassify any
            # interval after durable commit as handoff, even if polling learned
            # about the answer later. Outage intervals keep their own category.
            after = sum(max(0, end-max(start, at)) for state,start,end in self.segments
                        if state == "human_wait" and end >= self.ready_at)
            self.elapsed["human_wait"] -= after
            self.elapsed["handoff"] += after
            self.ready_at = None
            self.review_deadline_reached = False
            self.state = "handoff"

    @property
    def deadline(self):
        with self.guard:
            now = self._tick()
            remaining = self.limit - sum(self.elapsed[s] for s in self.ACTIVE)
            if self.interruption or self.state == "terminal" or remaining <= 0:
                return now
            return now + remaining if self.state in self.ACTIVE else math.inf

    def snapshot(self):
        with self.guard:
            self._tick()
            return {
                "state": self.state,
                "elapsed": dict(self.elapsed),
                "agent_seconds": sum(self.elapsed[s] for s in self.ACTIVE),
                "wall_seconds": self.last_wall - self.created,
                "interruption": self.interruption,
                "review_deadline_reached": self.review_deadline_reached,
            }
