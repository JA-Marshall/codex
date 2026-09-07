import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign_timing import analyze_campaign, write_report
from test_timing_report import request


def fixture():
    campaign = {"schema_version": 1, "campaign_id": "smoke", "jobs": 1,
                "measurement_purpose": "isolated-timing", "trials": [{"run_id": "trial-0001"}]}
    results = {"schema_version": 1, "campaign_id": "smoke", "total": 1, "trials": [{
        "run_id": "trial-0001", "status": "finished", "host_exit_code": 0,
        "evaluation_exit_code": 0, "worker_exit_code": 0, "task_success": True,
        "started_unix_ms": 0, "finished_unix_ms": 20000,
        "host_started_unix_ms": 1000, "host_finished_unix_ms": 11000,
    }]}
    runtimes = {"trial-0001": [{"type": "phase_thread_bound", "thread_id": "thread-a"}]}
    provider = request("1", "thread-a", 2000, 5000, 8000) + request("2", "thread-a", 3000, 6000, 9000)
    return campaign, results, runtimes, provider


class CampaignTimingTests(unittest.TestCase):
    def test_host_boundaries_exclude_fixture_and_grader_and_union_overlapping_waits(self):
        report = analyze_campaign(*fixture())
        row = report["runs"][0]
        self.assertEqual(
            (row["elapsed_ms"], row["request_wait_sum_ms"], row["queue_wait_union_ms"],
             row["observed_elapsed_excluding_queue_ms"], report["unknown_trials"]),
            (10000, 6000, 4000, 6000, 0),
        )
        self.assertTrue(row["isolated_timing_eligible"])
        self.assertIsNone(report["unthrottled_speed_estimate"])
        self.assertIn("fixture setup", report["elapsed_basis"])

    def test_full_trace_competing_traffic_and_host_failures_are_preserved(self):
        campaign, results, runtimes, provider = fixture()
        campaign.update(jobs=2, measurement_purpose="throughput")
        results["trials"][0].update(host_exit_code=1, task_success=False, failure_classification="scope_blocked")
        runtimes["trial-0001"].append({"type": "runtime_failed"})
        provider += request("foreign", "other-thread", 1500, 4000, 6000)
        row = analyze_campaign(campaign, results, runtimes, provider)["runs"][0]
        self.assertEqual(row["exclusion_reasons"], ["not_declared_isolated_timing", "concurrent_hosts",
                                                  "competing_proxy_requests", "runtime_failure", "host_failure"])
        self.assertEqual((row["competing_proxy_requests"], row["task_success"], row["failure_classification"]),
                         (1, False, "scope_blocked"))

    def test_never_started_missing_runtime_and_no_requests_remain_unknown(self):
        for variant in ("never_started", "missing_runtime", "no_requests"):
            campaign, results, runtimes, provider = fixture()
            record = results["trials"][0]
            if variant == "never_started":
                record.update(status="not_started", task_success=None, host_exit_code=None)
                record.pop("host_started_unix_ms")
                record.pop("host_finished_unix_ms")
            elif variant == "missing_runtime":
                runtimes.clear()
            else:
                provider = []
            row = analyze_campaign(campaign, results, runtimes, provider)["runs"][0]
            self.assertEqual(row["timing_status"], "unknown")
            self.assertIsNone(row["queue_wait_union_ms"])
            self.assertIsNone(row["request_wait_sum_ms"])
            self.assertIsNone(row["observed_elapsed_excluding_queue_ms"])
            self.assertFalse(row["isolated_timing_eligible"])
            self.assertEqual(row["status"], record["status"])

    def test_incomplete_trace_and_contradictory_lifetimes_fail_closed(self):
        for variant in ("trace_gap", "reversed", "outside", "duplicate_thread"):
            campaign, results, runtimes, provider = fixture()
            if variant == "trace_gap":
                provider.pop()
            elif variant == "reversed":
                results["trials"][0]["host_finished_unix_ms"] = 500
            elif variant == "outside":
                results["trials"][0]["host_started_unix_ms"] = 2500
            else:
                runtimes["trial-0001"] *= 2
            with self.assertRaises(ValueError, msg=variant):
                analyze_campaign(campaign, results, runtimes, provider)

    def test_unknown_host_overlap_still_disqualifies_claimed_isolation(self):
        campaign, results, runtimes, provider = fixture()
        campaign["trials"].append({"run_id": "trial-0002"})
        results["trials"].append({"run_id": "trial-0002", "host_started_unix_ms": 3000,
                                  "host_finished_unix_ms": 6000, "host_exit_code": 1})
        results["total"] = 2
        observed, unknown = analyze_campaign(campaign, results, runtimes, provider)["runs"]
        self.assertEqual(observed["exclusion_reasons"], ["concurrent_hosts"])
        self.assertFalse(observed["isolated_timing_eligible"])
        self.assertEqual(unknown["timing_status"], "unknown")

    def write_fixture(self, directory):
        campaign, results, runtimes, provider = fixture()
        root = directory / "campaign"
        root.mkdir()
        (root / "campaign.json").write_text(json.dumps(campaign))
        (root / "results.json").write_text(json.dumps(results))
        events = [{"schema_version": 1, "sequence": 1, "type": "campaign_started", "campaign_id": "smoke"},
                  {"schema_version": 1, "sequence": 2, "type": "campaign_finished", "total": 1}]
        (root / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
        for name, events in runtimes.items():
            runtime = root / "runs" / name
            runtime.mkdir(parents=True)
            (runtime / "runtime-events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
        trace = directory / "provider-events.jsonl"
        trace.write_text("".join(json.dumps(event) + "\n" for event in provider))
        return root / "campaign.json", trace, directory / "timing"

    def test_stopped_campaign_export_hashes_inputs_without_changing_them(self):
        with tempfile.TemporaryDirectory() as temp:
            campaign, trace, output = self.write_fixture(Path(temp))
            inputs = {path: path.read_bytes() for path in Path(temp).rglob("*") if path.is_file()}
            report = write_report(campaign, trace, output)
            self.assertEqual(len(report["input_sha256"]), 5)
            self.assertEqual({path: path.read_bytes() for path in inputs}, inputs)
            self.assertEqual(json.loads((output / "timing.json").read_text()), report)
            self.assertTrue((output / "README.md").is_file())
            with self.assertRaises(FileExistsError):
                write_report(campaign, trace, output)
            with self.assertRaisesRegex(ValueError, "separate"):
                write_report(campaign, trace, campaign.parent / "timing")

    def test_running_campaign_and_changed_trace_do_not_publish_a_report(self):
        with tempfile.TemporaryDirectory() as temp:
            campaign, trace, output = self.write_fixture(Path(temp))
            journal = campaign.parent / "events.jsonl"
            complete = journal.read_text()
            journal.write_text(complete.splitlines()[0] + "\n")
            with self.assertRaisesRegex(ValueError, "not terminal"):
                write_report(campaign, trace, output)
            journal.write_text(complete)

            def mutate_trace(*args):
                report = analyze_campaign(*args)
                with trace.open("a") as stream:
                    stream.write(json.dumps({"type": "trace_changed"}) + "\n")
                return report

            with patch("campaign_timing.analyze_campaign", mutate_trace):
                with self.assertRaisesRegex(ValueError, "changed during analysis"):
                    write_report(campaign, trace, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
