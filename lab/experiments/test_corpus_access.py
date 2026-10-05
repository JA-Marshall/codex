"""Held-out payload canaries stay unread even through parent/report indirection."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign_inputs import digest, read_json, write_json
from study_compare import load_lineage
from workflow_proposal import propose_revision
from study import run_once
from study_resume import prepare_resume


class CorpusAccessTest(unittest.TestCase):
    def test_heldout_run_and_resume_rejected_before_payload_loading_or_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "campaign.json"
            write_json(path, {"study_stage": "confirmation"})
            with (
                patch("study.load_campaign") as run_load,
                patch("study_resume.load_campaign") as resume_load,
            ):
                with self.assertRaisesRegex(ValueError, "custodian preregistration"):
                    run_once(path)
                with self.assertRaisesRegex(ValueError, "custodian preregistration"):
                    prepare_resume(path, root / "child")
                run_load.assert_not_called()
                resume_load.assert_not_called()
            self.assertFalse((root / "study-attempts").exists())
            self.assertFalse((root / "child").exists())

    def test_top_level_and_parent_heldout_results_are_never_read_or_hashed(self):
        for stage in ["validation", "confirmation"]:
            for parent in [False, True]:
                with (
                    self.subTest(stage=stage, parent=parent),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary)
                    heldout = root / "heldout"
                    heldout.mkdir()
                    write_json(
                        heldout / "campaign.json",
                        dict(study_stage=stage, campaign_id="sealed", trials=[]),
                    )
                    secret_result = heldout / "results.json"
                    secret_result.write_text(
                        "canary: even hashing this payload is forbidden"
                    )
                    target = heldout
                    if parent:
                        target = root / "development-child"
                        target.mkdir()
                        write_json(
                            target / "campaign.json",
                            dict(
                                study_stage="development",
                                campaign_id="child",
                                trials=[],
                                queue_resume=dict(
                                    parent_manifest=str(heldout / "campaign.json"),
                                    parent_manifest_sha256=digest(
                                        heldout / "campaign.json"
                                    ),
                                    parent_results_sha256="a" * 64,
                                ),
                            ),
                        )
                        write_json(
                            target / "results.json",
                            dict(campaign_id="child", trials=[]),
                        )

                    def safe_read(path, *args):
                        self.assertNotEqual(
                            Path(path), secret_result, "held-out results were read"
                        )
                        return read_json(path, *args)

                    def safe_hash(path):
                        self.assertNotEqual(
                            Path(path), secret_result, "held-out results were hashed"
                        )
                        return digest(path)

                    with (
                        patch("study_compare.read_json", side_effect=safe_read),
                        patch("study_compare.digest", side_effect=safe_hash),
                        patch("study_compare.summarize"),
                    ):
                        with self.assertRaisesRegex(ValueError, "custodian release"):
                            load_lineage(target)

    def test_proposal_rejects_heldout_stage_before_loading_pinned_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for index in range(2):
                path = root / f"arm-{index}.json"
                write_json(
                    path,
                    dict(study_stage="confirmation", variant={"id": f"arm-{index}"}),
                )
                paths.append(path)
            revision = root / "revision.json"
            write_json(
                revision,
                dict(
                    id="forbidden",
                    hypothesis="No held-out tuning",
                    incumbent_manifest=str(paths[0]),
                    challenger_manifest=str(paths[1]),
                    policy_change={},
                ),
            )
            with patch("workflow_proposal.load_campaign") as loaded:
                with self.assertRaisesRegex(ValueError, "development variants"):
                    propose_revision(revision, root / "registry")
                loaded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
