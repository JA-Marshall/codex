import argparse
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from campaign_inputs import (
    delegated_catalog,
    digest,
    freeze,
    load_campaign,
    read_json,
    validate_pins,
    write_json,
)


class CampaignInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_freeze_two_hundred_trials_is_offline_and_inputs_are_pinned(self):
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text('model = "test-model"\n')
        source = Path(__file__).resolve().parents[1]
        args = argparse.Namespace(
            binary=Path(sys.executable),
            sandbox=Path(sys.executable),
            codex_home=home,
            instruction_root=source,
            catalog=source / "workflows/queue-matrix-v2.toml",
            workflow=["queue-aaa-v2", "queue-aab-v2"],
            fixture=["durable-queue-v1"],
            repetitions=100,
            jobs=16,
            max_amendments=2,
            output=self.root / "frozen",
        )
        with patch("subprocess.Popen") as spawn:
            manifest = freeze(args)
        spawn.assert_not_called()
        self.assertEqual(len(manifest["trials"]), 200)
        self.assertFalse((args.output / "trials").exists())
        self.assertGreater(len(manifest["pins"]), 40)
        self.assertEqual(read_json(args.output / "campaign.json"), manifest)
        pinned = load_campaign(args.output / "campaign.json")
        self.assertEqual(
            pinned["manifest_sha256"], digest(args.output / "campaign.json")
        )
        with self.assertRaisesRegex(ValueError, "changed after scheduling"):
            load_campaign(args.output / "campaign.json", "0" * 64)
        bad = dict(manifest, jobs=100)
        write_json(args.output / "campaign.json", bad)
        with self.assertRaisesRegex(ValueError, "bounded campaign"):
            load_campaign(args.output / "campaign.json")
        write_json(args.output / "campaign.json", manifest)
        validate_pins(manifest)
        effective = Path(manifest["catalog"]).read_text()
        self.assertIn('approval = "campaign_delegated"', effective)
        self.assertNotIn('approval = "human_required"', effective)
        (home / "config.toml").write_text('model = "changed"\n')
        with self.assertRaisesRegex(ValueError, "input changed"):
            validate_pins(manifest)

    def test_catalog_changes_only_approval_semantics_and_rejects_bad_inheritance(self):
        source = """schema_version = 1
[workflows.base]
approval = 'human_required' # inherited
[workflows.test]
extends = "base"
"""
        changed, _ = delegated_catalog(source, ["test"])
        self.assertIn("approval = 'campaign_delegated' # inherited", changed)
        with self.assertRaisesRegex(ValueError, "unknown workflow"):
            delegated_catalog(source, ["missing"])
        with self.assertRaisesRegex(ValueError, "inheritance"):
            delegated_catalog(
                source.replace('extends = "base"', 'extends = "test"'), ["test"]
            )


if __name__ == "__main__":
    unittest.main()
