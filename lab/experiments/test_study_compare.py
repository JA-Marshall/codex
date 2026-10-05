import json
from pathlib import Path
import tempfile
import unittest

from campaign_inputs import digest, read_json, write_json
from study_compare import compare


def observed(entry, accepted):
    return dict(
        entry,
        status="finished",
        task_success=accepted,
        workflow_result=dict(
            run_id=entry["run_id"],
            workflow=entry["workflow"],
            task_id=entry["fixture"],
            workflow_status="completed",
            stop_status="confirmed",
            evaluation_status="completed",
            candidate_sha256="a" * 64,
            task_success=accepted,
            evidence={},
        ),
    )


class AdditiveReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parent = self.root / "parent"
        self.parent.mkdir()
        self.entries = [
            dict(run_id=f"trial-{index:04}", fixture="task", workflow=arm, repetition=1)
            for index, arm in ((1, "direct-v1"), (2, "our-v0"))
        ]
        self.manifest = dict(
            campaign_id="parent",
            output=str(self.parent),
            trials=self.entries,
            pins={},
            sdk_runtime={"budget": {"requests": 10}, "reasoning_effort": "medium"},
        )
        self.rows = [
            observed(self.entries[0], False),
            dict(self.entries[1], status="not_started", task_success=None),
        ]
        write_json(self.parent / "campaign.json", self.manifest)
        write_json(
            self.parent / "results.json", dict(campaign_id="parent", trials=self.rows)
        )

    def test_queue_report_reuses_parent_slot_once_and_retains_pair(self):
        child = self.root / "child"
        child.mkdir()
        claim = dict(
            output=str(child),
            parent_manifest_sha256=digest(self.parent / "campaign.json"),
            parent_results_sha256=digest(self.parent / "results.json"),
            run_ids=["trial-0002"],
        )
        from study_resume import derive_child

        write_json(self.parent / "queue-resume-claim.json", claim)
        write_json(
            child / "campaign.json",
            derive_child(
                self.manifest,
                self.parent / "campaign.json",
                child,
                [self.entries[1]],
                claim,
                "child",
            ),
        )
        write_json(
            child / "results.json",
            dict(campaign_id="child", trials=[observed(self.entries[1], True)]),
        )
        report = compare(child, self.root / "report")
        self.assertEqual(report["comparisons"][0]["paired_trials"], 1)
        self.assertEqual(report["arms"]["direct-v1"]["rejected"], 1)
        self.assertEqual(report["arms"]["our-v0"]["accepted"], 1)
        self.assertEqual(len(report["sources"]), 2)
        valid_child = read_json(child / "campaign.json")
        changed_child = read_json(child / "campaign.json")
        changed_child["sdk_runtime"]["budget"]["requests"] = 100
        changed_child["sdk_runtime"]["reasoning_effort"] = "high"
        write_json(child / "campaign.json", changed_child)
        with self.assertRaisesRegex(ValueError, "comparison conditions"):
            compare(child, self.root / "drift")
        write_json(child / "campaign.json", valid_child)
        changed_claim = dict(claim, output=str(self.root / "foreign-child"))
        write_json(self.parent / "queue-resume-claim.json", changed_claim)
        with self.assertRaisesRegex(ValueError, "exclusive parent queue claim"):
            compare(child, self.root / "claim-drift")
        write_json(self.parent / "queue-resume-claim.json", claim)
        self.rows[0]["task_success"] = True
        write_json(
            self.parent / "results.json", dict(campaign_id="parent", trials=self.rows)
        )
        with self.assertRaisesRegex(ValueError, "parent evidence changed"):
            compare(child, self.root / "changed")

    def correction(self):
        directory = self.parent / "trials/trial-0001"
        directory.mkdir(parents=True)
        write_json(directory / "result.json", self.rows[0])
        write_json(
            directory / "evaluation.json",
            {"task_success": False, "scope_success": True},
        )
        write_json(directory / "snapshot.json", {"candidate": "a" * 64})
        output = self.root / "correction"
        output.mkdir()
        entry = dict(
            run_id="trial-0001",
            original_result=str(directory / "result.json"),
            result_sha256=digest(directory / "result.json"),
            original_evaluation=str(directory / "evaluation.json"),
            evaluation_sha256=digest(directory / "evaluation.json"),
            snapshot=str(directory / "snapshot.json"),
            snapshot_sha256=digest(directory / "snapshot.json"),
        )
        write_json(
            output / "manifest.json",
            dict(
                original_campaign_sha256=digest(self.parent / "campaign.json"),
                entries=[entry],
            ),
        )
        record = dict(
            run_id="trial-0001",
            original_result_sha256=entry["result_sha256"],
            original_evaluation_sha256=entry["evaluation_sha256"],
            original_task_success=False,
            original_workflow_status="completed",
            candidate_sha256="a" * 64,
            replay_manifest_sha256=digest(output / "manifest.json"),
            corrected_task_success=True,
            original_scope_success=True,
            evaluation={"task_success": True},
            oracle_revision="diagnostics-v2",
        )
        write_json(output / "results.json", dict(model_calls=0, records=[record]))
        return output, digest(output / "manifest.json"), digest(output / "results.json")

    def test_correction_changes_only_derived_analysis_with_originals_visible(self):
        correction = self.correction()
        before = (self.parent / "results.json").read_bytes()
        report = compare(self.parent, self.root / "corrected-report", correction)
        self.assertEqual(report["arms"]["direct-v1"]["accepted"], 1)
        self.assertEqual(report["arms"]["direct-v1"]["rejected"], 0)
        self.assertEqual(
            report["original_oracle_counts_not_quality_failures"]["direct-v1"][
                "rejected"
            ],
            1,
        )
        self.assertEqual(
            report["oracle_correction"]["records"][0]["original_task_success"], False
        )
        self.assertEqual((self.parent / "results.json").read_bytes(), before)
        self.assertIn(
            "original False, corrected True",
            (self.root / "corrected-report/report.md").read_text(),
        )

    def test_correction_cannot_bind_a_different_candidate_or_changed_results(self):
        directory, manifest_hash, result_hash = self.correction()
        data = read_json(directory / "results.json")
        data["records"][0]["candidate_sha256"] = "b" * 64
        write_json(directory / "results.json", data)
        with self.assertRaisesRegex(ValueError, "selected hashes"):
            compare(
                self.parent, self.root / "bad1", (directory, manifest_hash, result_hash)
            )
        with self.assertRaisesRegex(ValueError, "candidate"):
            compare(
                self.parent,
                self.root / "bad2",
                (directory, manifest_hash, digest(directory / "results.json")),
            )


if __name__ == "__main__":
    unittest.main()
