"""Provider failures retain bounded typed cause through the actual SDK."""

import json
import unittest

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_failed


class TurnErrorTest(SdkFixture):
    def test_failed_response_retains_the_runtime_error(self):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("failure"),
                    ev_failed("failure", "provider-diagnostic-marker" + "Ω" * 5000),
                ]
            )
        )
        run = self.start()
        result = run.parent("Report a provider failure.")
        self.assertEqual(result["status"], "failed")
        self.assertIn("provider-diagnostic-marker", json.dumps(result["error"]))
        self.assertLessEqual(len(json.dumps(result["error"]).encode()), 8192)
        receipt = run.close()
        journal = [
            json.loads(line)
            for line in (run.artifacts / "session/session.jsonl")
            .read_text()
            .splitlines()
        ]
        completed = next(
            event for event in journal if event["type"] == "turn_completed"
        )
        self.assertEqual(completed["error"], result["error"])
        self.assertEqual(receipt["process"]["stop_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
