"""Projection, live-tail and HTTP boundary checks using temporary campaign data."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from server import CampaignStore, make_server


class DashboardTests(unittest.TestCase):
    def test_sdk_acceptance_is_separate_from_failed_workflow_and_live_session(self):
        self.write(
            "campaign.json",
            {
                "campaign_id": "campaign-1",
                "jobs": 2,
                "trials": [self.entry],
                "sdk_runtime": {"mode": "fixture"},
            },
        )
        self.events(
            "events.jsonl",
            [
                {"type": "campaign_started", "unix_ms": 1000},
                {"type": "trial_started", "run_id": "trial-0001", "unix_ms": 1100},
            ],
        )
        self.events(
            "runs/trial-0001/session/session.jsonl",
            [{"type": "session_stopped", "unix_ms": 1200}],
        )
        self.events(
            "runs/trial-0001/increment-1/session/session.jsonl",
            [{"type": "session_started", "unix_ms": 1300}],
        )
        active = self.store.campaign("smoke", now=1400)
        self.assertEqual(active["trials"][0]["phase"], "workflow")
        self.assertEqual(active["trials"][0]["latest_event_at"], 1300)
        self.assertEqual(self.store.campaign("smoke", now=1400), active)
        self.write(
            "trials/trial-0001/result.json",
            {
                **self.entry,
                "status": "finished",
                "task_success": True,
                "host_exit_code": 1,
                "evaluation_exit_code": 0,
                "workflow_result": {
                    "workflow_status": "failed",
                    "stop_status": "confirmed",
                    "evaluation_status": "completed",
                },
                "usage": {"input_tokens": 0, "output_tokens": None},
            },
        )
        finished = self.store.campaign("smoke", now=1500)
        self.assertEqual(
            [
                finished["accepted"],
                finished["rejected"],
                finished["acceptance_unknown"],
                finished["failed"],
            ],
            [1, 0, 0, 1],
        )
        self.assertEqual(finished["trials"][0]["workflow_status"], "failed")
        self.assertEqual(finished["trials"][0]["usage"]["input_tokens"], 0)
        self.assertIsNone(finished["trials"][0]["usage"]["output_tokens"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campaign = self.root / "campaigns" / "smoke"
        self.store = CampaignStore(self.root / "campaigns", self.root / "timing")
        self.entry = {
            "run_id": "trial-0001",
            "fixture": "bugfix",
            "workflow": "repair",
            "family": "bugfix",
            "language": "python",
        }
        self.write(
            "campaign.json",
            {
                "campaign_id": "campaign-1",
                "jobs": 12,
                "trials": [self.entry],
                "private_prompt": "DO NOT EXPOSE",
            },
        )

    def write(self, name, data):
        path = self.campaign / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def events(self, name, data, tail=""):
        path = self.campaign / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(item) + "\n" for item in data) + tail, encoding="utf-8"
        )

    def test_prepared_to_active_to_quiet_with_partial_live_tail(self):
        prepared = self.store.campaign("smoke", now=1500)
        self.assertEqual(
            (
                prepared["state"],
                prepared["total"],
                prepared["active"],
                prepared["trials"][0]["status"],
            ),
            ("prepared", 1, 0, "queued"),
        )
        self.events(
            "events.jsonl",
            [
                {"type": "campaign_started", "unix_ms": 1000},
                {"type": "trial_started", "run_id": "trial-0001", "unix_ms": 1100},
            ],
        )
        self.events(
            "runs/trial-0001/runtime-events.jsonl",
            [
                {
                    "type": "phase_started",
                    "epoch": 1,
                    "phase": "research",
                    "unix_ms": 1200,
                }
            ],
            '{"type":"phase_stopped"',
        )
        active = self.store.campaign("smoke", now=1500)
        self.assertEqual(
            (
                active["state"],
                active["trials"][0]["status"],
                active["trials"][0]["phase"],
                active["trials"][0]["elapsed_ms"],
            ),
            ("in_progress", "in_progress", "research", 400),
        )
        self.assertEqual(
            self.store.campaign("smoke", now=125000)["trials"][0]["status"], "quiet"
        )
        self.assertNotIn("DO NOT EXPOSE", json.dumps(active))

    def test_completed_result_phases_and_existing_audit(self):
        record = {
            **self.entry,
            "status": "finished",
            "task_success": True,
            "host_exit_code": 0,
            "evaluation_exit_code": 0,
            "worker_exit_code": 0,
            "started_unix_ms": 1100,
            "host_started_unix_ms": 1200,
            "host_finished_unix_ms": 1900,
            "finished_unix_ms": 2000,
            "public_test_success": True,
            "hidden_test_success": True,
            "error": "PRIVATE RAW LOG",
            "failure_classification": "PRIVATE RAW LOG",
        }
        self.write("results.json", {"trials": [record]})
        self.events(
            "events.jsonl",
            [
                {"type": "campaign_started", "unix_ms": 1000},
                {"type": "campaign_finished", "unix_ms": 2100},
            ],
        )
        self.events(
            "runs/trial-0001/runtime-events.jsonl",
            [
                {
                    "type": "phase_started",
                    "epoch": 1,
                    "phase": "research",
                    "unix_ms": 1250,
                },
                {"type": "phase_stopped", "epoch": 1, "unix_ms": 1500},
                {
                    "type": "phase_started",
                    "epoch": 2,
                    "phase": "research",
                    "unix_ms": 1550,
                },
                {"type": "phase_stopped", "epoch": 2, "unix_ms": 1850},
            ],
        )
        audit = self.root / "timing" / "smoke" / "audit" / "timing.json"
        audit.parent.mkdir(parents=True)
        audit.write_text(
            json.dumps(
                {
                    "campaign_id": "campaign-1",
                    "runs": [{"run_id": "trial-0001", "queue_wait_union_ms": 80}],
                }
            )
        )
        result = self.store.campaign("smoke", now=5000)
        trial = result["trials"][0]
        self.assertEqual(
            (
                result["state"],
                result["passed"],
                result["elapsed_ms"],
                trial["elapsed_ms"],
                trial["queue_wait_ms"],
            ),
            ("finished", 1, 1100, 700, 80),
        )
        self.assertEqual(
            trial["phases"],
            [
                {
                    "name": "research",
                    "status": "stopped",
                    "elapsed_ms": 250,
                    "started_at": 1250,
                },
                {
                    "name": "research",
                    "status": "stopped",
                    "elapsed_ms": 300,
                    "started_at": 1550,
                },
            ],
        )
        self.assertNotIn("PRIVATE RAW LOG", json.dumps(result))
        audit.write_text(
            json.dumps(
                {
                    "campaign_id": "another-campaign",
                    "runs": [{"run_id": "trial-0001", "queue_wait_union_ms": 80}],
                }
            )
        )
        self.assertIsNone(self.store.campaign("smoke")["trials"][0]["queue_wait_ms"])

    def test_cancelled_and_worker_failure_do_not_count_as_passes(self):
        self.write(
            "campaign.json",
            {"trials": [self.entry, {**self.entry, "run_id": "trial-0002"}]},
        )
        self.write(
            "results.json",
            {
                "cancelled": True,
                "trials": [
                    {
                        **self.entry,
                        "status": "finished",
                        "task_success": True,
                        "worker_exit_code": 1,
                    },
                    {"run_id": "trial-0002", "status": "not_started"},
                ],
            },
        )
        result = self.store.campaign("smoke")
        self.assertEqual(
            (
                result["state"],
                result["passed"],
                result["failed"],
                result["cancelled"],
                result["completed"],
            ),
            ("cancelled", 0, 1, 1, 2),
        )

    def test_worker_failure_freezes_elapsed_without_claiming_phase_shutdown(self):
        record = {**self.entry, "status": "failed", "worker_exit_code": 1}
        self.write("results.json", {"trials": [record]})
        self.events(
            "runs/trial-0001/runtime-events.jsonl",
            [
                {
                    "type": "phase_started",
                    "epoch": 1,
                    "phase": "research",
                    "unix_ms": 1200,
                }
            ],
        )
        starts = [
            {"type": "campaign_started", "unix_ms": 1000},
            {"type": "trial_started", "run_id": "trial-0001", "unix_ms": 1100},
        ]
        for endings, expected in (
            (
                [
                    {"type": "trial_finished", "unix_ms": 1800, "result": record},
                    {"type": "campaign_finished", "unix_ms": 2000},
                ],
                (1800, 700, 600),
            ),
            ([{"type": "campaign_finished", "unix_ms": 2000}], (2000, 900, 800)),
            ([], (None, None, None)),
        ):
            with self.subTest(endings=endings):
                self.events("events.jsonl", starts + endings)
                early = self.store.campaign("smoke", now=3000)["trials"][0]
                later = self.store.campaign("smoke", now=100000)["trials"][0]
                self.assertEqual(early, later)
                self.assertEqual(
                    (
                        early["finished_at"],
                        early["elapsed_ms"],
                        early["phases"][0]["elapsed_ms"],
                    ),
                    expected,
                )
                self.assertEqual(
                    (early["status"], early["phases"][0]["status"]),
                    ("failed", "shutdown_unknown"),
                )

    def test_containment_and_http_methods(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "campaign.json").write_text(json.dumps({"trials": []}))
        (self.store.root / "escape").symlink_to(outside, target_is_directory=True)
        for name in ("../outside", "escape"):
            with self.assertRaises(FileNotFoundError):
                self.store.campaign(name)
        server = make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            for method, path, expected in (
                ("GET", "/api/campaigns", 200),
                ("GET", "/api/campaigns/smoke", 200),
                ("HEAD", "/api/campaigns/smoke", 200),
                ("GET", "/api/campaigns/%2e%2e%2foutside", 404),
                ("GET", "/campaign.json", 404),
                ("POST", "/api/campaigns", 501),
                ("DELETE", "/api/campaigns/smoke", 501),
            ):
                connection.request(method, path)
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, expected, (method, path))
            connection.request(
                "GET", "/api/campaigns", headers={"Host": "attacker.invalid"}
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
