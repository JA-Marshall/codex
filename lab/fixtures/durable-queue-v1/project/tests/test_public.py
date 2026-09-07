import tempfile
import unittest
from pathlib import Path

from durable_queue import Queue


class QueueTests(unittest.TestCase):
    def test_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Queue(Path(tmp) / "queue.db")
            self.assertEqual(queue.list(), [])
            self.assertIsNone(queue.get("absent"))

    def test_submission_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.db"
            Queue(path).submit([{"id": "build", "payload": {"target": "all"}}])
            self.assertEqual(Queue(path).get("build")["payload"], {"target": "all"})

    def test_claim_dependency_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Queue(Path(tmp) / "queue.db")
            queue.submit([{"id": "build", "dependencies": ["setup"]}, {"id": "setup"}])
            claim = queue.claim("worker", 0, 10)
            self.assertEqual(claim["id"], "setup")
            queue.complete("setup", "worker", claim["attempts"], 1)
            self.assertEqual(queue.claim("worker", 1, 10)["id"], "build")
