import copy
import unittest

from timing_report import analyze, union_ms


def fixture():
    batch = {
        "jobs": 1,
        "measurement_purpose": "isolated-timing",
        "runs": [{"run_id": "a"}],
    }
    events = [
        {"type": "decision_sent", "run_id": "a", "unix_ms": 0},
        {"type": "host_exited", "run_id": "a", "unix_ms": 10000, "exit_code": 0},
    ]
    runtimes = {"a": [{"type": "phase_thread_bound", "thread_id": "thread-a"}]}
    return batch, events, runtimes


def request(name, thread, start, dispatched, end):
    return [
        {
            "type": "request_queued",
            "request_id": name,
            "client_request_id": thread,
            "unix_ms": start,
        },
        {
            "type": "request_dispatched",
            "request_id": name,
            "unix_ms": dispatched,
            "queued_ms": dispatched - start,
        },
        {"type": "request_finished", "request_id": name, "unix_ms": end},
    ]


class TimingTests(unittest.TestCase):
    def test_overlapping_queue_wait_is_not_double_subtracted(self):
        report = analyze(
            *fixture(),
            request("1", "thread-a", 1000, 4000, 7000)
            + request("2", "thread-a", 2000, 5000, 8000),
        )
        row = report["runs"][0]
        self.assertEqual(
            (
                row["elapsed_ms"],
                row["request_wait_sum_ms"],
                row["queue_wait_union_ms"],
                row["observed_elapsed_excluding_queue_ms"],
            ),
            (10000, 6000, 4000, 6000),
        )
        self.assertTrue(row["isolated_timing_eligible"])
        self.assertIsNone(report["unthrottled_speed_estimate"])

    def test_parallel_and_foreign_traffic_disqualify_speed_comparison(self):
        batch, events, runtimes = fixture()
        batch["jobs"] = 16
        batch["measurement_purpose"] = "throughput"
        row = analyze(
            batch,
            events,
            runtimes,
            request("1", "thread-a", 1000, 2000, 7000)
            + request("other", "unknown-thread", 1500, 3000, 4000),
        )["runs"][0]
        self.assertEqual(
            row["exclusion_reasons"],
            [
                "not_declared_isolated_timing",
                "concurrent_hosts",
                "competing_proxy_requests",
            ],
        )
        self.assertEqual(row["competing_proxy_requests"], 1)

    def test_observed_overlap_overrides_claimed_single_job(self):
        batch, events, runtimes = fixture()
        batch["runs"].append({"run_id": "b"})
        events += [
            {"type": "decision_sent", "run_id": "b", "unix_ms": 3000},
            {"type": "host_exited", "run_id": "b", "unix_ms": 12000, "exit_code": 0},
        ]
        runtimes["b"] = [{"type": "phase_thread_bound", "thread_id": "thread-b"}]
        report = analyze(
            batch,
            events,
            runtimes,
            request("1", "thread-a", 1000, 2000, 7000)
            + request("2", "thread-b", 4000, 5000, 9000),
        )
        self.assertTrue(
            all("concurrent_hosts" in r["exclusion_reasons"] for r in report["runs"])
        )

    def test_incomplete_duplicate_and_incompatible_clock_evidence_is_not_zero_wait(
        self,
    ):
        original = request("1", "thread-a", 1000, 2000, 7000)
        bad_clock = copy.deepcopy(original)
        bad_clock[1]["queued_ms"] = 2000
        for data in (original[:-1], original[1:], original + original, bad_clock):
            with self.assertRaises(ValueError):
                analyze(*fixture(), data)
        with self.assertRaisesRegex(ValueError, "missing requests"):
            analyze(*fixture(), request("1", "unknown", 1000, 2000, 7000))

    def test_cancelled_queue_and_failed_run_remain_visible(self):
        batch, events, runtimes = fixture()
        events[-1]["exit_code"] = 1
        runtimes["a"].append({"type": "runtime_failed"})
        rows = request("1", "thread-a", 1000, 2000, 7000)
        rows[1] = {"type": "request_cancelled", "request_id": "1", "unix_ms": 3000}
        row = analyze(batch, events, runtimes, rows)["runs"][0]
        self.assertEqual(row["queue_wait_union_ms"], 2000)
        self.assertEqual(row["exclusion_reasons"], ["runtime_failure", "host_failure"])

    def test_union_handles_disjoint_nested_and_touching_intervals(self):
        self.assertEqual(union_ms([(0, 10), (2, 3), (10, 15), (20, 25)]), 20)
        self.assertEqual(union_ms([]), 0)


if __name__ == "__main__":
    unittest.main()
