"""Budget reconciliation, missing usage, and atomic worker-group admission."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import time
import unittest

from provider_proxy import Journal
from workflows.usage import Budget, UsageLedger


class WorkflowUsageTest(unittest.TestCase):
    def test_request_limit_rejection_records_capacity_without_prompt(self):
        ledger = UsageLedger(
            "run", "pinned", Budget(1, 100000, 5, output_ceiling=1000), self.journal
        )
        ledger.register("worker")
        self.complete(self.admit(ledger, "worker", "first"))
        with self.assertRaises(ValueError):
            self.admit(ledger, "worker", "second")
        events = [
            json.loads(line)
            for line in (Path(self.temp.name) / "usage.jsonl").read_text().splitlines()
        ]
        rejected = next(
            event for event in events if event["type"] == "usage_group_rejected"
        )
        self.assertEqual(rejected["reasons"], ["request_limit"])
        self.assertEqual(rejected["admitted_requests"], 1)
        self.assertEqual(rejected["group_size"], 1)
        self.assertNotIn("input", rejected)

    def test_rejected_input_retains_size_and_reason_without_content(self):
        ledger = self.ledger()
        ledger.register("parent")
        body = json.dumps(
            {"model": "pinned", "input": "private-prompt-marker" * 11000}
        ).encode()
        with self.assertRaisesRegex(ValueError, "input_reservation_exceeded"):
            ledger.prepare(
                "rejected", body, {"X-Lab-Worker": "parent"}, "/v1/responses"
            )
        data = (Path(self.temp.name) / "usage.jsonl").read_text()
        event = json.loads(data.splitlines()[-1])
        self.assertEqual(event["type"], "usage_rejected")
        self.assertEqual(event["reason"], "input_reservation_exceeded")
        self.assertEqual(event["serialized_input_bytes"], len(body))
        self.assertEqual(event["input_ceiling"], ledger.budget.input_ceiling)
        self.assertNotIn("private-prompt-marker", data)
        self.assertEqual(ledger.snapshot()["requests"], 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Journal(Path(self.temp.name) / "usage.jsonl")
        self.addCleanup(self.journal.stream.close)

    def ledger(self, tokens=100000):
        return UsageLedger(
            "run", "pinned", Budget(20, tokens, 5, output_ceiling=1000), self.journal
        )

    def admit(self, ledger, worker, request):
        return ledger.prepare(
            request, b'{"model":"pinned"}', {"X-Lab-Worker": worker}, "/v1/responses"
        )[1]

    def complete(self, lease, *, cached=None):
        lease.dispatch()
        event = {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 30,
                    "output_tokens": 10,
                    "total_tokens": 40,
                    "input_tokens_details": {"cached_tokens": cached},
                }
            },
        }
        lease.feed(b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n\n")
        lease.finish(200)

    def test_reservations_wait_for_reconciliation_without_partial_group_dispatch(self):
        ledger = self.ledger(tokens=21000)
        ledger.register("parent")
        parent = self.admit(ledger, "parent", "p")
        ids = [str(i) for i in range(4)]
        ledger.declare_group(ids)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(self.admit, ledger, worker, worker) for worker in ids
            ]
            time.sleep(0.1)
            self.assertFalse(any(f.done() for f in futures))
            self.assertEqual(ledger.snapshot()["requests"], 1)
            self.complete(parent, cached=5)
            leases = [f.result(timeout=2) for f in futures]
            self.assertEqual(ledger.snapshot()["requests"], 5)
            self.assertFalse(ledger.stopped.is_set())
            for lease in leases:
                self.complete(lease, cached=5)
        snapshot = ledger.snapshot()
        self.assertEqual(
            (
                snapshot["observed_input_tokens"],
                snapshot["observed_output_tokens"],
                snapshot["observed_cached_input_tokens"],
                snapshot["charged_tokens"],
            ),
            (150, 50, 25, 200),
        )

    def test_group_that_cannot_fit_does_not_partially_start(self):
        ledger = self.ledger(tokens=10000)
        ids = [str(i) for i in range(4)]
        ledger.declare_group(ids)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(self.admit, ledger, worker, worker) for worker in ids
            ]
            for future in futures:
                with self.assertRaises(ValueError):
                    future.result(timeout=2)
        self.assertEqual(ledger.snapshot()["requests"], 0)

    def test_missing_usage_is_charged_conservatively_and_blocks_more_calls(self):
        ledger = self.ledger()
        ledger.register("worker")
        lease = self.admit(ledger, "worker", "first")
        lease.dispatch()
        lease.finish(502)
        lease.finish(502)
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["charged_tokens"], lease.reserve)
        self.assertEqual(snapshot["unknown_requests"], 1)
        self.assertIsNone(snapshot["observed_cached_input_tokens"])
        with self.assertRaises(ValueError):
            self.admit(ledger, "worker", "second")

    def test_foreign_worker_and_model_cannot_reach_provider(self):
        ledger = self.ledger()
        with self.assertRaises(ValueError):
            self.admit(ledger, "foreign", "first")
        ledger.register("worker")
        with self.assertRaises(ValueError):
            ledger.prepare(
                "second",
                b'{"model":"fallback"}',
                {"X-Lab-Worker": "worker"},
                "/v1/responses",
            )
        self.assertEqual(ledger.snapshot()["requests"], 0)


if __name__ == "__main__":
    unittest.main()
