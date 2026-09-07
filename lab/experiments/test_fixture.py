import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from evaluate_fixture import evaluate
from setup_fixture import FIXTURE, setup
from fixture_registry import fixture


class FixtureTests(unittest.TestCase):
    def test_structured_tasks_are_deterministic_and_calibrated(self):
        binary = Path(os.environ["CODEX_LAB_TEST_BINARY"]).resolve()
        for name in ("dependency-order-v1", "config-merge-v1"):
            with self.subTest(fixture=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                selected = fixture(name)
                first = setup(root / "fixture", name)
                second = setup(root / "repeat", name)
                self.assertEqual((first["commit"], first["files"]), (second["commit"], second["files"]))
                self.assertEqual(set(first["files"]), {".gitignore", "TASK.md", "cli.py", selected.module + ".py", "tests/test_public.py"})
                repository = root / "fixture/repository"
                module = repository / (selected.module + ".py")
                original = module.read_bytes()
                sandbox = root / "codex-linux-sandbox"
                sandbox.symlink_to(binary)
                for variant in ("baseline", "noop", "partial", "reference"):
                    if variant == "noop":
                        module.write_bytes(original + b"\n# Cosmetic change.\n")
                    elif variant == "partial":
                        module.write_text(
                            "def order_tasks(graph):\n    return sorted(graph, key=lambda n: len(graph[n]))\n"
                            if name == "dependency-order-v1" else
                            "def merge_config(base, override):\n    return dict(base, **override)\n"
                        )
                    elif variant == "reference":
                        shutil.copyfile(Path(__file__).with_name("reference_structured.py"), module)
                    result = evaluate(repository, sandbox, root / variant, root / "fixture/fixture.json")
                    self.assertEqual(result["task_success"], variant == "reference", json.dumps(result, indent=2))
                    self.assertEqual(result["hidden_test_success"], variant == "reference")
                    self.assertEqual(len(result["checks"]), len(selected.cases))

    def test_setup_pins_identical_commits_and_excludes_evaluator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = setup(root / "first")
            second = setup(root / "second")
            self.assertEqual(
                (first["commit"], first["tree"], first["files"]),
                (second["commit"], second["tree"], second["files"]),
            )
            self.assertEqual(
                set(first["files"]),
                {
                    ".gitignore",
                    "TASK.md",
                    "csv_summary.py",
                    "cli.py",
                    "tests/test_public.py",
                },
            )
            with self.assertRaises(FileExistsError):
                setup(root / "first")

    def test_evaluator_rejects_baseline_noop_partial_and_accepts_reference(self):
        binary = Path(os.environ["CODEX_LAB_TEST_BINARY"]).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sandbox = root / "codex-linux-sandbox"
            sandbox.symlink_to(binary)
            setup(root / "fixture")
            repository = root / "fixture/repository"
            fixture_manifest = root / "fixture/fixture.json"
            original = (repository / "csv_summary.py").read_bytes()
            for variant in ["baseline", "noop", "partial", "reference"]:
                if variant == "noop":
                    (repository / "csv_summary.py").write_bytes(
                        original + b"\n# No functional change.\n"
                    )
                elif variant == "partial":
                    (repository / "csv_summary.py").write_text(
                        "import csv, io\ndef summarize(text):\n"
                        "    rows = csv.reader(io.StringIO(text))\n    next(rows, None)\n"
                        "    result = {}\n    for category, count in rows:\n"
                        "        result[category] = result.get(category, 0) + int(count)\n    return result\n",
                        encoding="utf-8",
                    )
                elif variant == "reference":
                    shutil.copyfile(
                        Path(__file__).with_name("reference_csv_summary.py"),
                        repository / "csv_summary.py",
                    )
                    cli = (FIXTURE / "project/cli.py").read_text(encoding="utf-8")
                    (repository / "cli.py").write_text(
                        cli.replace(
                            'read_text(encoding="utf-8")',
                            'read_bytes().decode("utf-8")',
                        ),
                        encoding="utf-8",
                    )
                result = evaluate(repository, sandbox, root / variant, fixture_manifest)
                self.assertEqual(
                    result["task_success"],
                    variant == "reference",
                    json.dumps(result, indent=2),
                )
                self.assertEqual(result["hidden_test_success"], variant == "reference")
                self.assertFalse((repository / "evaluator-must-not-write").exists())
                self.assertTrue((root / variant / "evaluation.json").is_file())


if __name__ == "__main__":
    unittest.main()
