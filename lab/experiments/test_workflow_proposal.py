import json
from pathlib import Path
import sys
import tempfile
import unittest

from campaign_inputs import digest, read_json, write_json
from workflow_proposal import propose_revision


class WorkflowProposalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        self.hashes = []
        for index in (0, 1):
            output = self.root / str(index)
            archive = output / "inputs/lab"
            policy = archive / "experiments/workflows/our_v0.py"
            policy.parent.mkdir(parents=True)
            policy.write_text(f"repair_limit = {index + 1}\n")
            task = archive / "tasks/durable-queue-v1/manifest.json"
            task.parent.mkdir(parents=True)
            write_json(task, {"split": "development"})
            catalog = archive / "model-catalog.json"
            catalog.write_text("{}")
            manifest = dict(
                schema_version=1,
                campaign_id=str(index),
                approval="campaign_delegated",
                jobs=1,
                max_amendments=0,
                automatic_retries=0,
                resume_supported=False,
                output=str(output),
                archive=str(archive),
                python=sys.executable,
                task_root=str(archive / "tasks"),
                study_stage="development",
                variant={"id": f"variant-{index}"},
                sdk_runtime={"budget": {"requests": 10}, "model_catalog": str(catalog)},
                trials=[
                    dict(
                        run_id="trial-0001",
                        fixture="durable-queue-v1",
                        workflow="our-v0",
                        repetition=1,
                    )
                ],
                pins={str(path): digest(path) for path in (policy, task, catalog)},
            )
            path = output / "campaign.json"
            write_json(path, manifest)
            self.paths.append(path)
            self.hashes.append(digest(policy))
        self.revision = self.root / "revision.json"
        self.registry = self.root / "registry"
        self.value = dict(
            id="one-more-repair",
            hypothesis="An additional repair improves acceptance.",
            incumbent_manifest=str(self.paths[0]),
            challenger_manifest=str(self.paths[1]),
            policy_change=dict(
                path="experiments/workflows/our_v0.py",
                before_sha256=self.hashes[0],
                after_sha256=self.hashes[1],
                description="Increase repair limit by one.",
            ),
        )
        write_json(self.revision, self.value)

    def test_concrete_frozen_policy_difference_produces_no_launch_and_audit(self):
        proposal = read_json(propose_revision(self.revision, self.registry))
        self.assertEqual(proposal["paired_slots"], [["durable-queue-v1", 1]])
        self.assertEqual(proposal["model_calls"], 0)
        self.assertEqual(proposal["arms"][0]["sha256"], digest(self.paths[0]))
        self.assertEqual(
            [
                read_json(path)["kind"]
                for path in sorted((self.registry / "revision-attempts").glob("*.json"))
            ],
            ["proposal_received", "proposed"],
        )
        self.assertFalse((self.paths[0].parent / "events.jsonl").exists())

    def test_changed_budget_rejects_and_records_attempt(self):
        manifest = read_json(self.paths[1])
        manifest["sdk_runtime"]["budget"]["requests"] = 11
        write_json(self.paths[1], manifest)
        with self.assertRaisesRegex(ValueError, "budget"):
            propose_revision(self.revision, self.registry)
        self.assertEqual(
            [
                read_json(path)["kind"]
                for path in sorted((self.registry / "revision-attempts").glob("*.json"))
            ],
            ["proposal_received", "rejected"],
        )

    def test_extra_grader_difference_cannot_be_hidden_by_policy_label(self):
        manifest = read_json(self.paths[1])
        extra = Path(manifest["archive"]) / "grader.py"
        extra.write_text("accept_all = True\n")
        manifest["pins"][str(extra)] = digest(extra)
        write_json(self.paths[1], manifest)
        with self.assertRaisesRegex(ValueError, "single policy change"):
            propose_revision(self.revision, self.registry)

    def test_invalid_json_attempt_is_retained(self):
        self.revision.write_text("not json")
        with self.assertRaises(ValueError):
            propose_revision(self.revision, self.registry)
        self.assertEqual(
            len(list((self.registry / "revision-attempts").glob("*.json"))), 2
        )


if __name__ == "__main__":
    unittest.main()
