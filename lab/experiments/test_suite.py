import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from setup_suite import prepare_task, setup_suite, validate_pins


class SuiteTests(unittest.TestCase):
    def test_frozen_pair_setup_and_drift_refusal_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            catalog = home / "models.json"
            catalog.write_text("{}")
            (home / "config.toml").write_text(
                'model = "test-model"\nmodel_catalog_json = '
                + json.dumps(str(catalog))
                + "\n"
            )
            binary = Path(os.environ["CODEX_LAB_TEST_BINARY"])
            suite = setup_suite(root / "suite", binary, home)
            validate_pins(suite)
            for task in suite["tasks"]:
                left, right = [
                    json.loads(
                        Path(task["conditions"][short]["fixture_manifest"]).read_text()
                    )
                    for short in ("md", "json")
                ]
                self.assertEqual(
                    (left["commit"], left["files"], left["task_sha256"]),
                    (right["commit"], right["files"], right["task_sha256"]),
                )
                self.assertNotEqual(left["repository"], right["repository"])
                self.assertFalse(
                    (Path(left["repository"]) / "reference_structured.py").exists()
                )
            with self.assertRaises(FileExistsError):
                setup_suite(root / "suite", binary, home)
            frozen = (
                Path(suite["archive"]) / "instructions/verifier/tests-only-v1/SKILL.md"
            )
            frozen.write_text(frozen.read_text() + "\nChanged procedure\n")
            with patch("setup_suite.subprocess.run") as execute:
                with self.assertRaisesRegex(ValueError, "frozen suite input changed"):
                    prepare_task(root / "suite", "dependency-order-v1")
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
