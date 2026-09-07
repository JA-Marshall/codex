"""One paced rolling-window allowance shared by every request in a proxy process."""

from collections import deque
from contextlib import contextmanager
from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import threading
import time


class Cancelled(Exception):
    pass


class PacedWindow:
    def __init__(self, limit=100, window=60.0):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("request limit must be an integer from 1 to 100")
        if not math.isfinite(window) or window <= 0:
            raise ValueError("window must be positive and finite")
        self.limit, self.window = limit, window
        self.recent = deque()
        self.next_at = self.blocked_until = 0.0

    def delay(self, now):
        while self.recent and now - self.recent[0] >= self.window:
            self.recent.popleft()
        oldest = self.recent[0] + self.window if len(self.recent) >= self.limit else now
        return max(0.0, self.next_at - now, self.blocked_until - now, oldest - now)

    def record(self, now):
        self.recent.append(now)
        self.next_at = now + self.window / self.limit


class SharedLimiter:
    def __init__(self, limit=100, window=60.0, startup_delay=60.0):
        self.policy = PacedWindow(limit, window)
        self.policy.blocked_until = time.monotonic() + startup_delay
        self.condition = threading.Condition()
        self.waiting = deque()
        self.stopped = threading.Event()

    @contextmanager
    def dispatch(self, cancelled):
        """Serialize request writes, not response streams; count failed writes too."""
        ticket = object()
        with self.condition:
            self.waiting.append(ticket)
            try:
                while True:
                    if self.stopped.is_set() or cancelled():
                        raise Cancelled()
                    delay = self.policy.delay(time.monotonic())
                    if self.waiting[0] is ticket and delay <= 0:
                        break
                    self.condition.wait(timeout=min(max(delay, 0.01), 0.2))
                try:
                    yield
                finally:
                    # Recording after the write also paces delayed/socket-blocked
                    # senders; reservations cannot bunch up after a scheduling pause.
                    self.policy.record(time.monotonic())
            finally:
                self.waiting.remove(ticket)
                self.condition.notify_all()

    def cooldown(self, seconds):
        with self.condition:
            self.policy.blocked_until = max(
                self.policy.blocked_until, time.monotonic() + seconds
            )
            self.condition.notify_all()

    def stop(self):
        self.stopped.set()


def retry_after(value, now=None):
    """Honor delta seconds or HTTP dates; missing/invalid values cool down a minute."""
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            delay = date.timestamp() - (time.time() if now is None else now)
        except (ValueError, TypeError, OverflowError, AttributeError):
            return 60.0
    return max(0.0, delay) if math.isfinite(delay) else 60.0
