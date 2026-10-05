"""Run-wide admission and conservative accounting at the actual HTTP boundary."""

from dataclasses import dataclass
import json
import socket
import threading
import time

from provider_rate_limit import Cancelled


@dataclass(frozen=True)
class Budget:
    requests: int
    tokens: int
    seconds: float
    input_ceiling: int = 200000
    output_ceiling: int = 16000

    def __post_init__(self):
        if any(
            type(v) is not int or v <= 0
            for v in (
                self.requests,
                self.tokens,
                self.input_ceiling,
                self.output_ceiling,
            )
        ):
            raise ValueError("positive integer request/token limits required")
        if not 0 < self.seconds <= 86400:
            raise ValueError("finite deadline required")


class UsageLedger:
    def __init__(self, run_id, model, budget, journal, *, clock=None):
        self.run_id, self.model, self.budget, self.journal = (
            run_id,
            model,
            budget,
            journal,
        )
        self.guard = threading.RLock()
        self.condition = threading.Condition(self.guard)
        self.stopped = threading.Event()
        self.clock = clock
        self._deadline = time.monotonic() + budget.seconds
        self.pausing = False
        self.workers = set()
        self.active = {}
        self.groups = {}
        self.requests = self.observed_tokens = self.charged_tokens = self.reserved = (
            self.unknown
        ) = 0
        self.input_tokens = self.output_tokens = self.cached_input_tokens = 0

    @property
    def deadline(self):
        return self.clock.deadline if self.clock else self._deadline

    @deadline.setter
    def deadline(self, value):
        if self.clock is not None:
            raise RuntimeError("human trial deadline belongs to its shared clock")
        self._deadline = value

    def pause_admission(self):
        with self.guard:
            self.pausing = True
            self.condition.notify_all()

    def resume_admission(self):
        with self.guard:
            if self.stopped.is_set():
                raise RuntimeError("stopped admission cannot resume")
            self.pausing = False
            self.condition.notify_all()

    def declare_group(self, workers):
        with self.guard:
            group = {"workers": set(workers), "leases": [], "admitted": False}
            for worker in workers:
                self.register(worker)
                self.groups[worker] = group

    def register(self, worker_id):
        with self.guard:
            if (
                worker_id in self.workers
                or len(self.workers) >= 64
                or self.stopped.is_set()
            ):
                raise ValueError("worker admission rejected")
            self.workers.add(worker_id)

    def prepare(self, request_id, body, headers, path):
        with self.guard:
            worker = headers.get("X-Lab-Worker")
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeError):
                self._reject(request_id, worker, "invalid_request_json", len(body))
            if (
                worker not in self.workers
                or not isinstance(payload, dict)
                or payload.get("model") != self.model
            ):
                self._reject(
                    request_id,
                    worker,
                    "unattributed_request_or_model_mismatch",
                    len(body),
                )
            # A conservative byte bound, with protocol overhead, rather than an
            # unverified tokenizer estimate. Provider violations remain visible.
            if len(body) + 4096 > self.budget.input_ceiling:
                self._reject(
                    request_id, worker, "input_reservation_exceeded", len(body)
                )
            reserve = len(body) + 4096 + self.budget.output_ceiling
            if path == "/v1/responses":
                payload["max_output_tokens"] = self.budget.output_ceiling
            lease = RequestLease(self, request_id, worker, reserve, path)
            group = self.groups.pop(worker, None)
            if group:
                group["leases"].append(lease)
                if len(group["leases"]) == len(group["workers"]):
                    self._admit(group["leases"])
                    group["admitted"] = True
                    self.condition.notify_all()
                else:
                    while not group["admitted"]:
                        if self.stopped.is_set() or time.monotonic() >= self.deadline:
                            self.stop("incomplete_worker_group")
                            raise ValueError("worker group not admitted")
                        self.condition.wait(0.05)
            else:
                self._admit([lease])
            return json.dumps(payload).encode(), lease

    def _reject(self, request_id, worker, reason, body_bytes):
        self.journal.event(
            "usage_rejected",
            run_id=self.run_id,
            request_id=request_id,
            worker_id=worker if worker in self.workers else None,
            reason=reason,
            serialized_input_bytes=body_bytes,
            protocol_overhead_bytes=4096,
            input_ceiling=self.budget.input_ceiling,
            output_ceiling=self.budget.output_ceiling,
            admitted_requests=self.requests,
            request_limit=self.budget.requests,
            charged_tokens=self.charged_tokens,
            reserved_tokens=self.reserved,
            token_limit=self.budget.tokens,
        )
        raise ValueError(reason)

    def _admit(self, leases):
        reserve = sum(lease.reserve for lease in leases)
        while True:
            if self.pausing:
                self.journal.event("human_pause_admission_rejected", workers=[lease.worker for lease in leases])
                raise ValueError("human checkpoint admission closed")
            reasons = [
                reason
                for reason, hit in (
                    ("run_stopped", self.stopped.is_set()),
                    ("deadline_expired", time.monotonic() >= self.deadline),
                    (
                        "request_limit",
                        self.requests + len(leases) > self.budget.requests,
                    ),
                    (
                        "token_capacity",
                        self.charged_tokens + reserve > self.budget.tokens,
                    ),
                )
                if hit
            ]
            if reasons:
                self.journal.event(
                    "usage_group_rejected",
                    run_id=self.run_id,
                    reasons=reasons,
                    group_size=len(leases),
                    requested_reservation=reserve,
                    admitted_requests=self.requests,
                    request_limit=self.budget.requests,
                    charged_tokens=self.charged_tokens,
                    reserved_tokens=self.reserved,
                    token_limit=self.budget.tokens,
                )
                self.stop("budget_exhausted_or_group_exceeds_capacity")
                raise ValueError("budget cannot admit this request/group")
            if self.charged_tokens + self.reserved + reserve <= self.budget.tokens:
                break
            # Wait for existing reservations to reconcile; never dispatch a
            # partial initial reviewer group just to fit a temporary shortfall.
            self.condition.wait(0.05)
        for lease in leases:
            self.active[lease.id] = lease
            self.requests += 1
            self.reserved += lease.reserve
            self.journal.event(
                "usage_admitted",
                run_id=self.run_id,
                worker_id=lease.worker,
                request_id=lease.id,
                reserved_tokens=lease.reserve,
                path=lease.path,
                group_size=len(leases),
            )

    def stop(self, reason):
        with self.guard:
            if not self.stopped.is_set():
                self.journal.event(
                    "admission_stopped", run_id=self.run_id, reason=reason
                )
            self.stopped.set()
            self.condition.notify_all()
            for lease in list(self.active.values()):
                lease.abort()

    def snapshot(self):
        with self.guard:
            return {
                "run_id": self.run_id,
                "requests": self.requests,
                "observed_tokens": self.observed_tokens,
                "observed_input_tokens": self.input_tokens,
                "observed_output_tokens": self.output_tokens,
                "observed_cached_input_tokens": self.cached_input_tokens,
                "charged_tokens": self.charged_tokens,
                "reserved_tokens": self.reserved,
                "unknown_requests": self.unknown,
                "in_flight": len(self.active),
                "admission_stopped": self.stopped.is_set(),
            }


class RequestLease:
    def __init__(self, ledger, request_id, worker, reserve, path):
        self.ledger, self.id, self.worker, self.reserve, self.path = (
            ledger,
            request_id,
            worker,
            reserve,
            path,
        )
        self.connection = None
        self.dispatched = False
        self.buffer = b""
        self.usage = None
        self.invalid = False

    def cancelled(self):
        return self.ledger.stopped.is_set() or time.monotonic() >= self.ledger.deadline

    def attach(self, connection):
        self.connection = connection

    def dispatch(self):
        with self.ledger.guard:
            if self.cancelled():
                raise Cancelled()
            self.dispatched = True
            observer = getattr(self.ledger, "on_dispatch", None)
            if observer:
                observer(self.worker, self.id)
            self.ledger.journal.event(
                "usage_dispatched",
                run_id=self.ledger.run_id,
                worker_id=self.worker,
                request_id=self.id,
            )

    def abort(self):
        if self.connection and self.connection.sock:
            try:
                self.connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def feed(self, chunk):
        if self.invalid:
            return
        self.buffer += chunk
        if len(self.buffer) > 1024 * 1024:
            self.invalid = True
            self.buffer = b""
            return
        if self.path == "/v1/responses/compact":
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            if line[5:].strip() == b"[DONE]":
                continue
            try:
                event = json.loads(line[5:])
                if (
                    isinstance(event, dict)
                    and event.get("type") == "response.completed"
                ):
                    self._usage(event.get("response", {}).get("usage"))
            except (ValueError, AttributeError):
                self.invalid = True

    def _usage(self, usage):
        if not isinstance(usage, dict) or self.usage is not None:
            self.invalid = True
            return
        values = [
            usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
        ]
        if (
            any(type(v) is not int or v < 0 for v in values)
            or sum(values[:2]) != values[2]
        ):
            self.invalid = True
            return
        self.usage = {
            k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens")
        }
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        if cached is not None and (
            type(cached) is not int or not 0 <= cached <= values[0]
        ):
            self.invalid = True
        self.usage["cached_input_tokens"] = cached

    def finish(self, status):
        ledger = self.ledger
        with ledger.guard:
            if self.id not in ledger.active:
                return
            if self.path == "/v1/responses/compact" and not self.invalid:
                try:
                    self._usage(json.loads(self.buffer).get("usage"))
                except (ValueError, AttributeError):
                    self.invalid = True
            known = (
                self.dispatched
                and status == 200
                and self.usage is not None
                and not self.invalid
            )
            observed = self.usage["total_tokens"] if known else 0
            charged = observed if known else self.reserve if self.dispatched else 0
            ledger.reserved -= self.reserve
            ledger.observed_tokens += observed
            if known:
                ledger.input_tokens += self.usage["input_tokens"]
                ledger.output_tokens += self.usage["output_tokens"]
                cached = self.usage["cached_input_tokens"]
                ledger.cached_input_tokens = (
                    None
                    if cached is None or ledger.cached_input_tokens is None
                    else ledger.cached_input_tokens + cached
                )
            elif self.dispatched:
                ledger.cached_input_tokens = None
            ledger.charged_tokens += charged
            ledger.unknown += int(self.dispatched and not known)
            del ledger.active[self.id]
            ledger.condition.notify_all()
            ledger.journal.event(
                "usage_finished",
                run_id=ledger.run_id,
                worker_id=self.worker,
                request_id=self.id,
                dispatched=self.dispatched,
                known=known,
                usage=self.usage if known else None,
                charged_tokens=charged,
                status=status,
            )
            exceeded = known and (
                self.usage["input_tokens"] > self.reserve - ledger.budget.output_ceiling
                or self.usage["output_tokens"] > ledger.budget.output_ceiling
            )
            if self.dispatched and (not known or exceeded):
                ledger.stop("usage_unknown_or_provider_exceeded_reservation")
