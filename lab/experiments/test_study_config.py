import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from study_config import load_study


class StudyConfigTest(unittest.TestCase):
    def test_heldout_stage_rejected_before_any_task_discovery(self):
        self.write()
        self.config.write_text(
            self.config.read_text().replace(
                'stage="development"', 'stage="confirmation"'
            )
        )
        with patch("study_config.discover") as discover:
            with self.assertRaisesRegex(ValueError, "tuning cannot discover"):
                load_study(self.config)
            discover.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "study.toml"
        self.catalog = self.root / "catalog.toml"
        self.catalog.write_text(
            '[workflows.direct-v1]\napproval="human_required"\n[workflows."bmad-build-auto-v6.12.0"]\napproval="human_required"\n'
        )
        self.sdk = self.root / "sdk.json"
        self.sdk.write_text(
            json.dumps(
                dict(
                    project_recipe="stop-probe-followup-v1",
                    interaction_policy="delegated-task-v1",
                )
            )
        )
        self.paths = dict(
            binary=str(self.catalog),
            codex_home=str(self.root),
            catalog=str(self.catalog),
            instruction_root=str(self.root),
            sandbox=str(self.catalog),
            output=str(self.root / "output"),
            task_root=str(Path(__file__).resolve().parents[1] / "tasks/sentinels"),
            provider_service=str(self.sdk),
            sdk_config=str(self.sdk),
        )

    def write(self, workflow="direct-v1", task="py-checkout-change", sample=(), jobs=2):
        lines = ['stage="development"', f"jobs={jobs}", "[paths]"]
        lines.extend(key + "=" + json.dumps(value) for key, value in self.paths.items())
        lines += [
            "[[conditions]]",
            "workflow=" + json.dumps(workflow),
            "tasks=" + json.dumps([task]),
            "[storage]",
            "max_bytes=100000",
            "reserve_per_active_trial=100",
            "min_free_bytes=0",
            "debug_bytes_per_trial=100",
            "full_trace_sample=" + json.dumps(list(sample)),
        ]
        self.config.write_text("\n".join(lines))

    def test_documented_root_variant_registers_and_malformed_variant_fails_preflight(
        self,
    ):
        from campaign_inputs import write_json
        from study_ledger import register_variant

        self.write()
        original = self.config.read_text()
        self.config.write_text(
            original
            + '\n[variant]\nid="our-v0-initial"\nhypothesis="Preserved intent improves delivery."\nchange="Initial baseline."\n'
        )
        _, data, _ = load_study(self.config)
        self.assertIsNone(data["variant"]["parent"])
        manifest = self.root / "frozen.json"
        write_json(manifest, {"pins": {}})
        target = register_variant(self.root / "registry", data["variant"], manifest)
        self.assertTrue((target / "variant.json").is_file())
        self.config.write_text(original + '\n[variant]\nid="bad/id"\n')
        with self.assertRaises(ValueError):
            load_study(self.config)
        self.assertFalse((self.root / "output").exists())

    def test_valid_evolving_config_and_sample_preflight(self):
        self.write(sample=["trial-0001"])
        args, data, pairs = load_study(self.config)
        self.assertEqual(pairs, {("direct-v1", "py-checkout-change")})
        self.assertEqual(args.jobs, 2)
        self.assertEqual(data["storage"]["full_trace_sample"], ["trial-0001"])

    def test_unsupported_recipe_and_unknown_workflow_rejected_before_freeze(self):
        for workflow in ("bmad-build-auto-v6.12.0", "missing"):
            with self.subTest(workflow=workflow), self.assertRaises(ValueError):
                self.write(workflow=workflow)
                load_study(self.config)

    def test_legacy_owner_and_evolving_tasks_require_verified_capability(self):
        del self.paths["sdk_config"]
        for task in ("py-checkout-change", "py-retention-owner"):
            with self.subTest(task=task), self.assertRaisesRegex(ValueError, "legacy"):
                self.write(task=task)
                load_study(self.config)

    def test_invalid_trace_sample_and_sdk_concurrency_rejected(self):
        for sample, jobs in (
            (["unknown"], 2),
            (["trial-0001", "trial-0001"], 2),
            ([], 3),
        ):
            with self.subTest(sample=sample, jobs=jobs), self.assertRaises(ValueError):
                self.write(sample=sample, jobs=jobs)
                load_study(self.config)

    def test_legacy_budget_is_explicit_validated_and_cannot_override_sdk(self):
        budget = "\n[legacy_budget]\nrequests=120\ntokens=4000000\nseconds=1800\ninput_ceiling=500000\noutput_ceiling=16000\n"
        self.write(task="py-archive-intent")
        self.config.write_text(self.config.read_text() + budget)
        with self.assertRaisesRegex(ValueError, "cannot override an SDK"):
            load_study(self.config)
        del self.paths["sdk_config"]
        self.write(task="py-archive-intent")
        base = self.config.read_text()
        self.config.write_text(base + budget)
        _, data, _ = load_study(self.config)
        self.assertEqual(data["legacy_budget"]["requests"], 120)
        self.config.write_text(base + budget.replace("requests=120", "requests=0"))
        with self.assertRaises(ValueError):
            load_study(self.config)


if __name__ == "__main__":
    unittest.main()
