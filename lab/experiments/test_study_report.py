"""Known paired data expose unknowns, duplicate attempts, and clustered repeats."""

import unittest

from study_report import comparison, summarize, markdown


def row(project, workflow, accepted, repetition=1):
    return {
        "project_id": project,
        "fixture": project,
        "workflow": workflow,
        "task_success": accepted,
        "repetition": repetition,
    }


class StudyReportTest(unittest.TestCase):
    def test_frozen_tracks_and_owner_diagnostic_have_separate_denominators(self):
        planned, observed = [], []
        for index, facets in enumerate(
            (
                {},
                {"track": "A"},
                {"track": "B"},
                {"track": "A", "evaluation_group": "interaction-diagnostic"},
            )
        ):
            entry = {
                "run_id": str(index),
                "fixture": "task-" + str(index),
                "workflow": "direct-v1",
                "repetition": 1,
                **facets,
            }
            planned.append(entry)
            observed.append({**entry, "status": "not_started", "task_success": None})
        manifest = {"campaign_id": "study", "output": "/tmp/study", "trials": planned}
        result = {"campaign_id": "study", "trials": observed}
        report = summarize(manifest, result)
        self.assertEqual(
            set(report["strata"]),
            {
                "unspecified / unspecified",
                "A / unspecified",
                "B / unspecified",
                "A / interaction-diagnostic",
            },
        )
        self.assertEqual(report["comparisons"], [])
        self.assertIsNone(report["direct_saturated"])
        self.assertIn("pooled saturation is not applicable", report["next_decision"])
        self.assertTrue(
            all(
                value["arms"]["direct-v1"]["planned"] == 1
                for value in report["strata"].values()
            )
        )
        observed[-1]["evaluation_group"] = "clear-intent"
        with self.assertRaisesRegex(ValueError, "facets"):
            summarize(manifest, result)

    def test_unrelated_arm_does_not_add_unmatched_pairs(self):
        result = comparison(
            [
                row("one", "left", True),
                row("one", "right", True),
                row("two", "third", False),
            ],
            "left",
            "right",
        )
        self.assertEqual(result["unmatched_trial_keys"], 0)
        self.assertEqual(result["paired_trials"], 1)

    def test_repeated_trials_do_not_multiply_project_weight(self):
        rows = []
        for repetition in range(1, 10):
            rows.extend(
                [
                    row("one", "left", False, repetition),
                    row("one", "right", True, repetition),
                ]
            )
        rows.extend([row("two", "left", True), row("two", "right", False)])
        result = comparison(rows, "left", "right")
        self.assertEqual(result["paired_projects"], 2)
        self.assertEqual(result["paired_trials"], 10)
        self.assertEqual(result["project_weighted_delta"], 0)
        self.assertEqual(result["unknown_outcome_bounds"], [0, 0])
        self.assertEqual(result["project_hoeffding_95_bound"], [-1, 1])

    def test_unknown_outcomes_are_bounds_not_zeroes_or_dropped_pairs(self):
        result = comparison(
            [
                row("one", "left", True),
                row("one", "right", None),
                row("two", "left", False),
                row("two", "right", True),
            ],
            "left",
            "right",
        )
        self.assertIsNone(result["project_weighted_delta"])
        self.assertEqual(result["unknown_pairs"], 1)
        self.assertEqual(result["unknown_outcome_bounds"], [0, 0.5])
        self.assertIsNone(result["project_bootstrap_95_percent"])

    def test_duplicate_pair_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            comparison(
                [row("one", "left", True), row("one", "left", False)], "left", "right"
            )

    def test_report_separates_correct_product_failed_workflow_and_unknown_usage(self):
        planned = [
            {
                "run_id": "one",
                "workflow": "direct-v1",
                "fixture": "task",
                "repetition": 1,
            }
        ]
        manifest = {"campaign_id": "study", "output": "/tmp/study", "trials": planned}
        result = {
            "campaign_id": "study",
            "trials": [
                {
                    **planned[0],
                    "task_success": True,
                    "workflow_result": {
                        "run_id": "one",
                        "workflow": "direct-v1",
                        "task_id": "task",
                        "workflow_status": "failed",
                        "stop_status": "confirmed",
                        "evaluation_status": "completed",
                        "candidate_sha256": "a" * 64,
                        "task_success": True,
                        "evidence": {},
                    },
                    "usage": {"input_tokens": 0, "output_tokens": None},
                }
            ],
        }
        report = summarize(manifest, result)
        arm = report["arms"]["direct-v1"]
        self.assertEqual(
            [arm["accepted"], arm["workflow_failed"], arm["unknown"]], [1, 1, 0]
        )
        self.assertEqual(
            arm["usage"]["input_tokens"], {"known_total": 0, "unknown_runs": 0}
        )
        self.assertEqual(
            arm["usage"]["output_tokens"], {"known_total": 0, "unknown_runs": 1}
        )
        self.assertEqual(
            arm["usage"]["requests"], {"known_total": 0, "unknown_runs": 1}
        )
        result["trials"][0]["workflow_result"]["evidence"] = {
            "failure_phase": "followup",
            "turn_error": {
                "message": "study admission rejected",
                "codexErrorInfo": "other",
            },
            "runtime": {
                "usage": {
                    "requests": 120,
                    "charged_tokens": 2700000,
                    "admission_stopped": True,
                }
            },
        }
        detailed = summarize(manifest, result)
        self.assertEqual(
            detailed["arms"]["direct-v1"]["usage"]["requests"],
            {"known_total": 120, "unknown_runs": 0},
        )
        self.assertEqual(detailed["failure_examples"][0]["failure_phase"], "followup")
        self.assertIn(
            "study admission rejected",
            detailed["failure_examples"][0]["turn_error_summary"],
        )
        self.assertIn("| direct-v1 | 120 | 0 | 2700000 | 0 |", markdown(detailed))
        self.assertTrue(report["direct_saturated"])
        self.assertEqual(len(report["failure_examples"]), 1)
        result["trials"][0]["workflow_result"]["workflow_status"] = "unknown"
        rendered = markdown(summarize(manifest, result))
        self.assertIn("Workflow unknown | Not started", rendered)
        self.assertIn("| direct-v1 | 1 | 0 | 0 | 0 | 1 | 0 | unknown |", rendered)
        result["trials"] = []
        with self.assertRaisesRegex(ValueError, "every planned trial"):
            summarize(manifest, result)

    def test_all_project_wins_do_not_claim_zero_uncertainty(self):
        rows = [
            row(project, arm, arm == "right")
            for project in ("one", "two")
            for arm in ("left", "right")
        ]
        result = comparison(rows, "left", "right")
        self.assertEqual(result["project_weighted_delta"], 1)
        self.assertLess(result["project_hoeffding_95_bound"][0], 1)
