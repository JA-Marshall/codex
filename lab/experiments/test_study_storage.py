import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from study_storage import disk_admission, policy, retain_debug


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.root = self.output / "runs/trial-0001"
        self.home = self.root / "session/home"
        (self.home / "sessions").mkdir(parents=True)
        self.rollout = self.home / "sessions/rollout.jsonl"
        self.rollout.write_bytes(b"x" * 30)
        for name in ("logs_2.sqlite", "logs_2.sqlite-wal", "logs_2.sqlite-shm"):
            (self.home / name).write_bytes(b"y" * 30)
        self.essential = self.root / "usage.jsonl"
        self.essential.write_text("essential")
        (self.home / "state_5.sqlite").write_bytes(b"state")
        self.entry = {"run_id": "trial-0001"}
        self.limits = dict(
            max_bytes=10000,
            reserve_per_active_trial=100,
            min_free_bytes=0,
            debug_bytes_per_trial=100,
            full_trace_sample=[],
        )
        self.manifest = dict(
            output=str(self.output), trials=[self.entry], storage_policy=self.limits
        )
        self.record = dict(
            task_success=True,
            workflow_result=dict(
                stop_status="confirmed",
                workflow_status="completed",
                evidence={"runtime": {"provider_handlers_stopped": True}},
            ),
        )

    def test_unknown_stop_preserves_all_files(self):
        self.record["workflow_result"]["stop_status"] = "unknown"
        self.assertEqual(
            retain_debug(self.manifest, self.entry, self.record)["action"], "retained"
        )
        self.assertTrue(self.rollout.exists())
        self.assertFalse((self.root / "retention.json").exists())

    def test_success_removes_only_known_debug_and_receipts_hashes(self):
        receipt = retain_debug(self.manifest, self.entry, self.record)
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(len(receipt["files"]), 4)
        self.assertFalse(self.rollout.exists())
        self.assertFalse((self.home / "logs_2.sqlite-wal").exists())
        self.assertEqual(self.essential.read_text(), "essential")
        self.assertEqual((self.home / "state_5.sqlite").read_bytes(), b"state")
        self.assertEqual(retain_debug(self.manifest, self.entry, self.record), receipt)

    def test_selected_debug_budget_keeps_sqlite_group_whole(self):
        self.limits["full_trace_sample"] = ["trial-0001"]
        receipt = retain_debug(self.manifest, self.entry, self.record)
        self.assertTrue(self.rollout.exists())
        self.assertEqual(sum(row["retained_bytes"] for row in receipt["files"]), 30)
        self.assertTrue(
            all(
                not (self.home / name).exists()
                for name in ("logs_2.sqlite", "logs_2.sqlite-wal", "logs_2.sqlite-shm")
            )
        )

    def test_interruption_keeps_predeletion_receipt_and_does_not_retry(self):
        with patch.object(Path, "unlink", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                retain_debug(self.manifest, self.entry, self.record)
        receipt = json.loads((self.root / "retention.json").read_text())
        self.assertEqual(receipt["status"], "planned")
        self.assertEqual(len(receipt["files"]), 4)
        self.assertEqual(retain_debug(self.manifest, self.entry, self.record), receipt)
        self.assertTrue(self.rollout.exists())

    def test_sample_is_unique_and_planned(self):
        for sample in (["trial-0001", "trial-0001"], ["missing"]):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                policy(dict(self.limits, full_trace_sample=sample), ["trial-0001"])

    def test_admission_counts_existing_bytes_and_active_reservations(self):
        self.limits["max_bytes"] = 250
        self.assertTrue(disk_admission(self.manifest, 0)["admit"])
        self.assertFalse(disk_admission(self.manifest, 1)["admit"])


if __name__ == "__main__":
    unittest.main()
