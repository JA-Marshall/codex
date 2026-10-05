"""Real sandbox calibration is required before issuing a development certificate."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from campaign_inputs import digest, freeze, load_campaign
from corpus_calibration import certify_development, verify_certificate
from corpus_manifest import fingerprint
from task_library import calibrate
from task_registry import inventory, load_task
from study_config import freeze_study


class CorpusCalibrationTest(unittest.TestCase):
    def test_heldout_rejected_before_pack_or_calibration_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps({"split": "confirmation"}))
            with patch("corpus_calibration.load_task") as loaded:
                with self.assertRaisesRegex(ValueError, "separate custodian"):
                    certify_development(
                        root,
                        root / "absent-authoring",
                        root / "absent-calibration",
                        root / "output",
                    )
                loaded.assert_not_called()

    def test_actual_calibration_certificate_rejects_missing_rows_tampered_evidence_and_stale_assets(
        self,
    ):
        if sys.platform != "linux" or not os.environ.get("CODEX_STUDY_TEST_BINARY"):
            self.skipTest("actual Linux sandbox required")
        with tempfile.TemporaryDirectory(prefix="corpus-cert-") as temporary:
            root = Path(temporary)
            task_root = root / "development/archive"
            shutil.copytree(
                Path(__file__).resolve().parents[1]
                / "tasks/sentinels/py-archive-intent",
                task_root,
            )
            task = load_task(task_root)
            roles = dict.fromkeys(task.manifest["mutants"], "regression")
            roles.update(
                {
                    "delete-history": "wrong-interpretation",
                    "duplicate-audit": "visible-test-only",
                }
            )
            authoring = task_root / "authoring.json"
            authoring.write_text(
                json.dumps(
                    dict(
                        schema_version=1,
                        task_id=task.name,
                        project_id=task.manifest["project_id"],
                        lineage_id="archive-source",
                        duplicate_family="archive-family",
                        mutant_roles=roles,
                    )
                )
            )
            sandbox = root / "codex-linux-sandbox"
            sandbox.symlink_to(os.environ["CODEX_STUDY_TEST_BINARY"])
            with contextlib.redirect_stdout(io.StringIO()):
                report = calibrate({task.name: task}, root / "calibration", sandbox)
            report_path = root / "calibration/calibration.json"
            output = root / "certificates" / (task.name + ".json")
            self.assertTrue(report["calibrated"])
            self.assertEqual(
                report["task_inputs"][task.name], fingerprint(inventory(task_root))
            )
            self.assertEqual(
                certify_development(task_root, authoring, report_path, output), output
            )
            entry = dict(
                id=task.name,
                project_id=task.manifest["project_id"],
                lineage_id="archive-source",
                duplicate_family="archive-family",
                content_sha256=fingerprint(inventory(task_root)),
                calibration_sha256=digest(output),
            )
            verify_certificate(output, entry)
            saved_certificate = output.read_bytes()
            output.write_text(json.dumps({"calibrated": True}))
            with self.assertRaisesRegex(ValueError, "incomplete development"):
                verify_certificate(
                    output, dict(entry, calibration_sha256=digest(output))
                )
            output.write_bytes(saved_certificate)
            self.check_frozen_certificate(root, task, entry, output, sandbox)
            original = report_path.read_bytes()
            report["records"].pop()
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "every mutant"):
                certify_development(
                    task_root, authoring, report_path, root / "missing.json"
                )
            report_path.write_bytes(original)
            report = json.loads(original)
            row = next(
                row for row in report["records"] if row["variant"] == "duplicate-audit"
            )
            evaluation_path = Path(row["evaluation"])
            original_evaluation = evaluation_path.read_bytes()
            evaluation = json.loads(original_evaluation)
            evaluation["public_test_success"] = False
            evaluation_path.write_text(json.dumps(evaluation))
            row["evaluation_sha256"] = digest(evaluation_path)
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "actually pass public"):
                certify_development(
                    task_root, authoring, report_path, root / "bad-public.json"
                )
            evaluation_path.write_bytes(original_evaluation)
            report_path.write_bytes(original)
            (task_root / "project/src/app.py").write_text("stale calibration")
            with self.assertRaisesRegex(ValueError, "current task assets"):
                certify_development(
                    task_root, authoring, report_path, root / "stale.json"
                )

    def check_frozen_certificate(self, root, task, certified, certificate, sandbox):
        from test_corpus_manifest import entry

        item = entry(0, "development", "A")
        item.update(certified)
        index = root / "corpus.json"
        index.write_text(
            json.dumps(
                dict(
                    schema_version=1,
                    id="development-test",
                    state="draft",
                    development_root="development",
                    custodian_seal_sha256=None,
                    entries=[item],
                )
            )
        )
        home = root / "profile"
        home.mkdir()
        (home / "config.toml").write_text('model="test-model"\n')
        service = root / "service.json"
        service.write_text("{}")
        lab = Path(__file__).resolve().parents[1]
        paths = dict(
            binary=str(Path(sys.executable).resolve()),
            codex_home=str(home),
            catalog=str(lab / "workflows/repository-v2.toml"),
            instruction_root=str(lab),
            sandbox=str(sandbox),
            output=str(root / "frozen"),
            task_root=str(root / "development"),
            provider_service=str(service),
            corpus_index=str(index),
        )
        lines = ['stage="development"', "jobs=1", "[paths]"] + [
            key + "=" + json.dumps(value) for key, value in paths.items()
        ]
        lines += [
            "[[conditions]]",
            'workflow="repository-v2"',
            "tasks=" + json.dumps([task.name]),
            "[storage]",
            "max_bytes=100000000",
            "reserve_per_active_trial=1000",
            "min_free_bytes=0",
            "debug_bytes_per_trial=1000",
            "full_trace_sample=[]",
        ]
        config = root / "study.toml"
        config.write_text("\n".join(lines))
        with (
            patch("campaign_inputs.freeze_service", return_value=(None, {})),
            patch("subprocess.Popen") as launch,
        ):
            manifest = freeze_study(config)
        launch.assert_not_called()
        frozen_certificate = Path(manifest["corpus"]["certificates"][task.name])
        self.assertEqual(digest(frozen_certificate), digest(certificate))
        self.assertIn(str(frozen_certificate), manifest["pins"])
        original = certificate.read_bytes()
        certificate.write_text("external source changed after freeze")
        load_campaign(root / "frozen/campaign.json")
        certificate.write_bytes(original)
        frozen_certificate.write_text("tampered frozen certificate")
        with self.assertRaisesRegex(ValueError, "input changed"):
            load_campaign(root / "frozen/campaign.json")
        config.write_text(
            config.read_text().replace(str(root / "frozen"), str(root / "bad-freeze"))
        )

        def changed_frozen_grader(args):
            result = freeze(args)
            grader = Path(result["archive"]) / "experiments/task_registry.py"
            grader.write_text(grader.read_text() + "\n# changed after copying\n")
            result["pins"][str(grader)] = digest(grader)
            return result

        with (
            patch("campaign_inputs.freeze_service", return_value=(None, {})),
            patch("study_config.freeze", side_effect=changed_frozen_grader),
        ):
            with self.assertRaisesRegex(ValueError, "frozen evaluator"):
                freeze_study(config)


if __name__ == "__main__":
    unittest.main()
