import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from campaign_inputs import freeze, load_campaign
from evaluate_task import check_cases, evaluate, matches
from run_campaign import trial_commands
from task_library import calibrate, overlay
from task_registry import discover, load_task, setup
from test_terminal_run import make_run, write_json


def example(root):
    root.mkdir(parents=True)
    for directory in ("project/src", "project/tests", "solution/src",
                      "mutants/lower/src", "mutants/extra/src", "private"):
        (root / directory).mkdir(parents=True)
    manifest = {
        "schema_version": 1, "id": "example-task", "family": "extension",
        "language": "python", "size": "small", "split": "development",
        "project_id": "example-project", "capabilities": ["cli"],
        "write_paths": ["src", "tests"], "build": [], "structural_checks": [],
        "command": ["{python}", "{repository}/src/main.py"],
        "public_command": ["{python}", "-m", "unittest", "discover", "-s", "tests"],
        "mutants": ["lower", "extra"],
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "TASK.md").write_text("Uppercase the input and preserve its newline. Keep the CLI interface.\n")
    (root / "project/src/main.py").write_text("import sys\nsys.stdout.write(sys.stdin.read())\n")
    (root / "solution/src/main.py").write_text("import sys\nsys.stdout.write(sys.stdin.read().upper())\n")
    (root / "mutants/lower/src/main.py").write_text("import sys\nsys.stdout.write(sys.stdin.read().lower())\n")
    (root / "mutants/extra/src/main.py").write_text("import sys\nprint(sys.stdin.read().upper())\n")
    (root / "project/tests/test_public.py").write_text(
        "import subprocess, sys, unittest\nclass Public(unittest.TestCase):\n"
        " def test_cli(self):\n"
        "  result = subprocess.run([sys.executable, 'src/main.py'],input='hello\\n',text=True,capture_output=True)\n"
        "  self.assertEqual((result.returncode,result.stdout),(0,'HELLO\\n'))\n")
    (root / "private/cases.json").write_text(json.dumps([
        {"id": "unicode", "steps": [{"stdin": "straße\n", "expect": {"exit": 0, "stdout": "STRASSE\n"}}]},
        {"id": "empty", "steps": [{"stdin": "", "expect": {"exit": 0, "stdout": ""}}]},
    ]))
    return load_task(root)


class RepositoryTaskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.task = example(self.root / "library/example")

    def tearDown(self):
        self.temporary.cleanup()

    def sandbox(self):
        binary = os.environ.get("CODEX_LAB_TEST_BINARY")
        if sys.platform != "linux" or not binary:
            self.skipTest("real Linux sandbox requires CODEX_LAB_TEST_BINARY")
        return Path(binary).parent / "codex-linux-sandbox"

    def test_real_sandbox_calibration_rejects_baseline_and_both_mutants(self):
        result = calibrate({self.task.name: self.task}, self.root / "calibration", self.sandbox())
        self.assertEqual((result["tasks"], result["variants"], result["calibrated"], result["model_calls"]),
                         (1, 4, True, 0))

    def test_mutated_public_tests_do_not_replace_frozen_checks(self):
        metadata = setup(self.root / "candidate", self.task)
        repository = Path(metadata["repository"])
        (repository / "tests/test_public.py").write_text("# pretend everything passes\n")
        (repository / "tests/test_000.py").write_text("import unittest\nunittest.TestCase.run = lambda *a, **k: None\n")
        result = evaluate(repository, self.sandbox(), self.root / "grade", self.root / "candidate/fixture.json")
        self.assertFalse(result["public_test_success"])
        self.assertFalse(result["task_success"])

    def test_expected_files_preserve_exact_line_endings(self):
        (self.root / "data").write_bytes(b"a\r\n")
        result = {"timeout": False, "output_truncated": False, "exit_code": 0, "stdout": "", "stderr": ""}
        self.assertTrue(matches(result, {"exit": 0, "files": {"data": "a\r\n"}}, self.root))
        self.assertFalse(matches(result, {"exit": 0, "files": {"data": "a\n"}}, self.root))

    def test_stderr_tokens_follow_contract_without_requiring_adjacent_words(self):
        expected = {"exit": 2, "stderr_contains_all": ["conflict", "id"]}
        result = {"timeout": False, "output_truncated": False, "exit_code": 2,
                  "stdout": "", "stderr": "id x has a conflict\n"}
        check_cases([{"id": "tokens", "steps": [{"expect": expected}]}])
        self.assertTrue(matches(result, expected, self.root))
        self.assertFalse(matches(dict(result, stderr="conflict\n"), expected, self.root))
        self.assertFalse(matches(dict(result, invalid_utf8=True), expected, self.root))
        with self.assertRaisesRegex(ValueError, "invalid private expectation"):
            check_cases([{"id": "tokens", "steps": [{"expect": dict(expected, stderr_contains_all="id")}]}])

    def test_private_cases_cannot_read_previous_case_files(self):
        metadata = setup(self.root / "candidate", self.task)
        repository = Path(metadata["repository"])
        (repository / "src/main.py").write_text(
            "import pathlib, sys\nvalue = sys.stdin.read()\n"
            "try:\n leaked = pathlib.Path('../case-0/sentinel').read_text()\n"
            "except OSError:\n leaked = ''\n"
            "if pathlib.Path.cwd().name == 'case-0': pathlib.Path('sentinel').write_text('leaked')\n"
            "sys.stdout.write(value.upper() + leaked)\n")
        result = evaluate(repository, self.sandbox(), self.root / "grade", self.root / "candidate/fixture.json")
        self.assertTrue(result["task_success"])

    def test_scope_must_deny_the_frozen_task_asset_root(self):
        metadata = setup(self.root / "candidate", self.task)
        snapshot = Mock()
        snapshot.json.return_value = {"scope": {"write_paths": metadata["write_paths"], "deny_read_paths": []}}
        with patch("evaluate_task.observe_terminal", return_value=(snapshot, {}, {"task_scope_sha256": "a" * 64})):
            with self.assertRaisesRegex(ValueError, "protect private task assets"):
                evaluate(Path(metadata["repository"]), self.sandbox(), self.root / "grade",
                         self.root / "candidate/fixture.json", self.root / "run")

    def test_repository_task_run_requires_scoped_runtime_evidence(self):
        metadata = setup(self.root / "fixture", self.task)
        run = self.root / "run"
        make_run(run)
        repository = Path(metadata["repository"])
        write_json(run / "config/run-spec.json", {"repository": {"commit": metadata["commit"]}, "task": (repository / "TASK.md").read_text()})
        with self.assertRaisesRegex(ValueError, "lacks its fixed task scope"):
            evaluate(repository, self.sandbox(), self.root / "grade", self.root / "fixture/fixture.json", run)

    def test_changed_private_cases_are_refused(self):
        metadata = setup(self.root / "candidate", self.task)
        (self.task.root / "private/cases.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "assets or evaluator changed"):
            evaluate(Path(metadata["repository"]), self.sandbox(), self.root / "grade",
                     self.root / "candidate/fixture.json")

    def test_scope_changes_fail_even_when_code_is_correct(self):
        metadata = setup(self.root / "candidate", self.task)
        repository = Path(metadata["repository"])
        overlay(self.task.root / "solution", repository)
        (repository / "TASK.md").write_text("unrequested replacement")
        result = evaluate(repository, self.sandbox(), self.root / "grade", self.root / "candidate/fixture.json")
        self.assertTrue(result["public_test_success"] and result["hidden_test_success"])
        self.assertEqual(result["scope_violations"], ["TASK.md"])
        self.assertFalse(result["task_success"])

    def test_discovery_rejects_links_duplicate_ids_and_split_leakage(self):
        second = self.root / "library/second"
        shutil.copytree(self.task.root, second)
        with self.assertRaisesRegex(ValueError, "duplicate task"):
            discover(self.root / "library")
        data = json.loads((second / "manifest.json").read_text())
        data.update(id="second-task", split="confirmation")
        (second / "manifest.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "ancestry"):
            discover(self.root / "library")
        if sys.platform == "linux":
            (self.task.root / "project/src/escape").symlink_to("/etc/passwd")
            with self.assertRaisesRegex(ValueError, "link or special"):
                load_task(self.task.root)

    def test_campaign_freezes_custom_task_and_uses_repository_evaluator(self):
        source = Path(__file__).resolve().parents[1]
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text('model = "test-model"\n')
        args = argparse.Namespace(binary=Path(sys.executable), sandbox=Path(sys.executable),
                                  codex_home=home, instruction_root=source,
                                  catalog=source / "workflows/queue-matrix-v2.toml",
                                  workflow=["queue-aaa-v2"], fixture=[self.task.name],
                                  repetitions=3, jobs=2, max_amendments=0,
                                  output=self.root / "campaign", task_root=self.root / "library")
        with patch("subprocess.Popen") as spawn:
            frozen = freeze(args)
        spawn.assert_not_called()
        manifest = load_campaign(args.output / "campaign.json")
        self.assertEqual((len(manifest["trials"]), manifest["trials"][0]["family"]), (3, "extension"))
        self.assertEqual(manifest["task_ids"], [self.task.name])
        metadata = setup(self.root / "candidate", self.task)
        _, evaluator = trial_commands(manifest, frozen["trials"][0], metadata, self.root / "trial")
        self.assertTrue(evaluator[1].endswith("evaluate_task.py"))
        (Path(manifest["task_root"]) / self.task.name / "private/cases.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "input changed"):
            load_campaign(args.output / "campaign.json")

    def test_frozen_sandbox_alias_executes_independent_grading(self):
        sandbox = self.sandbox()
        source = Path(__file__).resolve().parents[1]
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text('model = "test-model"\n')
        args = argparse.Namespace(binary=sandbox.resolve(), sandbox=sandbox,
                                  codex_home=home, instruction_root=source,
                                  catalog=source / "workflows/queue-matrix-v2.toml",
                                  workflow=["queue-aaa-v2"], fixture=[self.task.name],
                                  repetitions=1, jobs=1, max_amendments=0,
                                  output=self.root / "campaign", task_root=self.root / "library")
        manifest = freeze(args)
        frozen = discover(manifest["task_root"])[self.task.name]
        metadata = setup(self.root / "candidate", frozen)
        repository = Path(metadata["repository"])
        overlay(frozen.root / "solution", repository)
        result = evaluate(repository, Path(manifest["sandbox"]), self.root / "grade",
                          self.root / "candidate/fixture.json")
        self.assertTrue(result["task_success"])


if __name__ == "__main__":
    unittest.main()
