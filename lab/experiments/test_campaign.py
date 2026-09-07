import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from campaign_inputs import digest, read_json
from run_campaign import coordinate, run_trial


FAKE_WORKER = r"""
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); name=sys.argv[2]
directory=root/'trials'/name
(directory/'entered').touch()
time.sleep(.015)
if name=='trial-0002': sys.exit(7)
result={'run_id':name,'status':'finished','host_exit_code':7 if name=='trial-0004' else 0,'evaluation_exit_code':0,
        'task_success':name!='trial-0003','usage':{'input_tokens':5,'output_tokens':2,'cached_input_tokens':0}}
(directory/'result.json').write_text(json.dumps(result))
"""

FAKE_STAGE = r"""
import json,sys
from pathlib import Path
mode,root=sys.argv[1],Path(sys.argv[2])
if mode=='host':
    phase=root/'runs/trial-0001/evidence'; phase.mkdir(parents=True)
    (phase/'phase-01.json').write_text(json.dumps({'token_usage':{'total_token_usage':{'input_tokens':9,'output_tokens':3,'cached_input_tokens':1}}}))
    sys.exit(7)
out=root/'trials/trial-0001/evaluation'; out.mkdir()
(out/'evaluation.json').write_text(json.dumps({'task_success':True,'public_test_success':True,'hidden_test_success':True}))
"""


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fake = self.root / "worker.py"
        self.fake.write_text(FAKE_WORKER)
        self.output = self.root / "campaign"
        self.output.mkdir()
        self.manifest = dict(
            campaign_id="test-campaign",
            output=str(self.output),
            pins={},
            jobs=3,
            python=sys.executable,
            archive=str(self.root),
            max_amendments=1,
            catalog=str(self.fake),
            trials=[],
        )

    def tearDown(self):
        self.temp.cleanup()

    def entries(self, count):
        self.manifest["trials"] = [
            dict(
                run_id=f"trial-{index:04}", fixture="durable-queue-v1", workflow="test"
            )
            for index in range(1, count + 1)
        ]

    def fake_command(self, manifest, entry):
        return [sys.executable, str(self.fake), manifest["output"], entry["run_id"]]

    def test_isolated_timing_is_serial_and_rejects_parallel_hosts(self):
        self.entries(2)
        self.manifest["measurement_purpose"] = "isolated-timing"
        with patch("run_campaign.worker_command") as command:
            with self.assertRaisesRegex(ValueError, "requires jobs=1"):
                coordinate(self.manifest)
        command.assert_not_called()
        self.assertFalse((self.output / "events.jsonl").exists())
        self.manifest["jobs"] = 1
        with patch("run_campaign.worker_command", self.fake_command), contextlib.redirect_stdout(io.StringIO()):
            result = coordinate(self.manifest)
        events = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        self.assertEqual([event["active_jobs"] for event in events if event["type"] == "trial_started"], [1, 1])
        self.assertEqual(result["measurement_purpose"], "isolated-timing")

    def test_hundred_subprocess_trials_are_bounded_and_failures_are_retained(self):
        self.entries(100)
        with (
            patch("run_campaign.worker_command", self.fake_command),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = coordinate(self.manifest)
        self.assertEqual(
            (result["total"], result["passed"], result["failed"]), (100, 97, 3)
        )
        self.assertEqual(
            (
                result["workflow_completed"],
                result["task_passed"],
                result["task_failed"],
                result["evaluation_failures"],
                result["evaluation_unknown"],
            ),
            (98, 98, 1, 0, 1),
        )
        self.assertEqual(
            result["usage"]["input_tokens"], {"known_total": 495, "unknown_trials": 1}
        )
        events = [
            json.loads(line)
            for line in (self.output / "events.jsonl").read_text().splitlines()
        ]
        active = [event["active_jobs"] for event in events if "active_jobs" in event]
        self.assertEqual(max(active), 3)
        self.assertEqual(
            sum(event["type"] == "trial_finished" for event in events), 100
        )
        self.assertEqual(len(list((self.output / "trials").iterdir())), 100)
        self.assertEqual(result["trials"][1]["status"], "failed")
        self.assertIs(result["trials"][2]["task_success"], False)
        with self.assertRaises(FileExistsError):
            coordinate(self.manifest)

    def test_cancellation_stops_pending_admissions_and_drains_live_workers(self):
        self.entries(100)
        stop = threading.Event()
        admitted = []
        gate = threading.Lock()

        def command(manifest, entry):
            with gate:
                admitted.append(entry["run_id"])
                if len(admitted) == manifest["jobs"]:
                    stop.set()
            return self.fake_command(manifest, entry)

        with (
            patch("run_campaign.worker_command", command),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = coordinate(self.manifest, stop)
        self.assertEqual(len(admitted), 3)
        self.assertEqual(result["not_started"], 97)
        self.assertTrue(result["cancelled"])
        self.assertTrue((self.output / "trials/trial-0001/result.json").is_file())
        self.assertFalse((self.output / "trials/trial-0004").exists())

    def test_cancel_before_launch_records_every_pending_trial(self):
        self.entries(5)
        stop = threading.Event()
        stop.set()
        with patch("run_campaign.worker_command") as command:
            result = coordinate(self.manifest, stop)
        command.assert_not_called()
        self.assertEqual(result["not_started"], 5)
        self.assertEqual(
            [record["status"] for record in result["trials"]], ["not_started"] * 5
        )

    def test_failed_host_still_evaluates_and_policy_binds_frozen_catalog_and_task(self):
        self.entries(1)
        (self.output / "trials/trial-0001").mkdir(parents=True)
        self.fake.write_text(FAKE_STAGE)

        def setup(destination, fixture):
            repository = destination / "repository"
            repository.mkdir(parents=True)
            (repository / "TASK.md").write_text("complete this task\n")
            return dict(repository=str(repository), commit="a" * 40)

        def commands(manifest, entry, metadata, directory):
            return (
                [sys.executable, str(self.fake), "host", str(self.output)],
                [sys.executable, str(self.fake), "evaluate", str(self.output)],
            )

        with (
            patch("run_campaign.setup_trial", setup),
            patch("run_campaign.trial_commands", commands),
            patch("run_campaign.time.time_ns", side_effect=[1000000, 2000000, 3000000, 4000000]),
        ):
            record = run_trial(self.manifest, self.manifest["trials"][0])
        self.assertEqual(
            (
                record["host_exit_code"],
                record["evaluation_exit_code"],
                record["task_success"],
            ),
            (7, 0, True),
        )
        self.assertEqual(
            [record[key] for key in ("started_unix_ms", "host_started_unix_ms", "host_finished_unix_ms", "finished_unix_ms")],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            record["usage"],
            {"input_tokens": 9, "output_tokens": 3, "cached_input_tokens": 1},
        )
        directory = self.output / "trials/trial-0001"
        original_result = (directory / "result.json").read_bytes()
        with (
            self.assertRaises(FileExistsError),
            patch("run_campaign.run_logged") as launch,
        ):
            run_trial(self.manifest, self.manifest["trials"][0])
        launch.assert_not_called()
        self.assertEqual((directory / "result.json").read_bytes(), original_result)
        policy = read_json(directory / "policy.json")
        self.assertEqual(
            policy,
            dict(
                schema_version=1,
                campaign_id="test-campaign",
                run_id="trial-0001",
                repository=str(directory / "fixture/repository"),
                repository_commit="a" * 40,
                task_sha256=digest(directory / "fixture/repository/TASK.md"),
                workflow="test",
                workflow_catalog_sha256=digest(self.fake),
                max_amendments=1,
            ),
        )


if __name__ == "__main__":
    unittest.main()
