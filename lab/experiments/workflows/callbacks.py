"""Bounded daemon callbacks and a cancellable host-owned user-input channel."""

from concurrent.futures import Executor, Future
import json
import queue
import threading
import time


class CallbackPool(Executor):
    def __init__(self):
        self.pending = queue.Queue(maxsize=8)
        self.closed = threading.Event()
        self.threads = [
            threading.Thread(target=self._work, daemon=True) for _ in range(5)
        ]
        for thread in self.threads:
            thread.start()

    def submit(self, fn, /, *args, **kwargs):
        if self.closed.is_set():
            raise RuntimeError("callbacks closed")
        future = Future()
        self.pending.put_nowait((future, fn, args, kwargs))
        return future

    def _work(self):
        while not self.closed.is_set():
            try:
                future, fn, args, kwargs = self.pending.get(timeout=0.05)
            except queue.Empty:
                continue
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(fn(*args, **kwargs))
                except BaseException as exc:
                    future.set_exception(exc)

    def close(self, timeout=1):
        self.closed.set()
        while True:
            try:
                self.pending.get_nowait()[0].cancel()
            except queue.Empty:
                break
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in self.threads)


class UserInput:
    def __init__(self, cancelled):
        self.cancelled = cancelled
        self.questions = queue.Queue(maxsize=4)

    def ask(self, params):
        if len(json.dumps(params).encode()) > 16384:
            raise ValueError("user question exceeds limit")
        answer = Future()
        self.questions.put_nowait((params, answer))
        while not self.cancelled.wait(0.05):
            if answer.done():
                value = answer.result()
                ids = {q["id"] for q in params["questions"]}
                if (
                    not isinstance(value, dict)
                    or set(value) != ids
                    or any(
                        not isinstance(items, list)
                        or any(not isinstance(s, str) for s in items)
                        for items in value.values()
                    )
                    or len(json.dumps(value).encode()) > 16384
                ):
                    raise ValueError("invalid user answers")
                return {
                    "answers": {key: {"answers": items} for key, items in value.items()}
                }
        raise RuntimeError("user interaction cancelled")
