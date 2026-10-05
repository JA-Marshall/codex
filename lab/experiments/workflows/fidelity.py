"""Bounded invocation evidence for auditing the stock workflow transport."""

import hashlib
import json
import threading


class Fidelity:
    def __init__(self, path):
        self.path = path
        self.path.touch(exist_ok=False)
        self.lock = threading.Lock()
        self.size = self.events = 0
        self.complete = True

    def record(self, kind, **fields):
        payload = (
            json.dumps({"type": kind, **fields}, ensure_ascii=False).encode() + b"\n"
        )
        with self.lock:
            if not self.complete:
                return
            if (
                len(payload) > 512 * 1024
                or self.size + len(payload) > 16 * 1024 * 1024
                or self.events >= 20000
            ):
                self.complete = False
                return
            with self.path.open("ab") as stream:
                stream.write(payload)
            self.size += len(payload)
            self.events += 1

    def snapshot(self):
        with self.lock:
            with self.path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            return {
                "complete": self.complete,
                "events": self.events,
                "bytes": self.size,
                "sha256": digest,
            }
