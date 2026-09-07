import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from campaign_inputs import freeze, load_campaign, validate_pins, write_json
from campaign_tasks import archive_just, just_helper
from run_campaign import run_trial, setup_trial
from task_registry import load_task, setup, task_text


@unittest.skipUnless(sys.platform == "linux", "campaign task helpers require Linux")
class TaskHelperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = self.root / "tasks"
        self.library.mkdir()
        self.helper = self.root / "external tools/just"
        self.helper.parent.mkdir()
        self.helper.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$RUSTC\" \"$RUSTDOC\" \"$(command -v cargo)\" \"$@\"\n")
        self.helper.chmod(0o755)
        self.rust = {"task": SimpleNamespace(manifest={"language": "rust"})}

    def tearDown(self):
        self.temporary.cleanup()

    def test_rust_selection_requires_an_external_executable_helper(self):
        args = argparse.Namespace(task_root=self.library, task_just=None)
        self.assertIsNone(just_helper(args, {}))
        with self.assertRaisesRegex(ValueError, "require --task-just"):
            just_helper(args, self.rust)
        args.task_just = self.helper
        self.assertEqual(just_helper(args, self.rust), self.helper.resolve())
        with self.assertRaisesRegex(ValueError, "requires a Rust"):
            just_helper(args, {})
        inside = self.library / "just"
        inside.write_bytes(self.helper.read_bytes())
        inside.chmod(0o755)
        args.task_just = inside
        with self.assertRaisesRegex(ValueError, "overlap task assets"):
            just_helper(args, self.rust)
        args.task_just = self.helper
        self.helper.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "executable file"):
            just_helper(args, self.rust)

    def test_archiving_preserves_mode_and_refuses_to_overwrite(self):
        archive = self.root / "archive"
        archive.mkdir()
        self.assertEqual(archive_just(archive, None), {})
        copied = Path(archive_just(archive, self.helper)["task_just"])
        self.assertEqual(copied, archive / "task-tools/just")
        self.assertEqual(copied.read_bytes(), self.helper.read_bytes())
        self.assertTrue(os.access(copied, os.X_OK))
        self.helper.write_text("replacement\n")
        with self.assertRaises(FileExistsError):
            archive_just(archive, self.helper)
        self.assertNotEqual(copied.read_bytes(), self.helper.read_bytes())

    def test_frozen_campaign_pins_helper_and_supplies_narrow_read_scope(self):
        source = Path(__file__).resolve().parents[1]
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text('model = "test-model"\n')
        catalog = self.root / "catalog.toml"
        catalog.write_text('[workflows.demo]\napproval = "human_required"\n')
        toolchain = self.root / "rust tools"
        (toolchain / "bin").mkdir(parents=True)
        for name in ("cargo", "rustc", "rustdoc"):
            executable = toolchain / "bin" / name
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
        args = argparse.Namespace(
            binary=Path(sys.executable), sandbox=Path(sys.executable), codex_home=home,
            instruction_root=source, catalog=catalog, workflow=["demo"],
            fixture=["rust_ranges"], repetitions=1, jobs=1, max_amendments=0,
            output=self.root / "frozen campaign", task_root=source / "tasks/rust",
            task_toolchain=toolchain, task_just=self.helper)
        with patch("subprocess.Popen") as spawn:
            manifest = freeze(args)
        spawn.assert_not_called()
        helper = Path(manifest["task_just"])
        self.assertEqual(helper, args.output / "inputs/lab/task-tools/just")
        self.assertIn(str(helper), manifest["pins"])
        self.assertNotIn(str(self.helper), manifest["pins"])
        load_campaign(args.output / "campaign.json")
        metadata = setup_trial(self.root / "prepared", "rust_ranges", manifest["task_root"],
                               manifest["task_toolchain"], manifest["task_just"])
        self.assertEqual(metadata["task_just"], str(helper))
        repository = Path(metadata["repository"])
        prompt = (repository / "TASK.md").read_text()
        command = prompt.split("```sh\n", 1)[1].split("\n```", 1)[0]
        result = subprocess.run(["/bin/sh", "-c", command], cwd=repository,
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), [str(toolchain / "bin/rustc"),
                         str(toolchain / "bin/rustdoc"), str(toolchain / "bin/cargo"),
                         "--justfile", "justfile", "test"])
        entry = manifest["trials"][0]
        directory = args.output / "trials" / entry["run_id"]
        directory.mkdir(parents=True)
        with patch("run_campaign.setup_trial", return_value=metadata), \
             patch("run_campaign.check_service"), \
             patch("run_campaign.run_logged", return_value=1) as run_logged:
            run_trial(manifest, entry)
        self.assertEqual(run_logged.call_count, 2)
        policy = json.loads((directory / "policy.json").read_text())
        self.assertEqual(policy["task_scope"]["read_paths"],
                         [str(Path(sys.base_prefix).resolve()), str(toolchain), str(helper.parent)])
        changed = dict(manifest)
        changed.pop("task_just")
        write_json(args.output / "campaign.json", changed)
        with self.assertRaisesRegex(ValueError, "helper must be pinned"):
            load_campaign(args.output / "campaign.json")
        helper.write_bytes(helper.read_bytes() + b"# altered\n")
        with self.assertRaisesRegex(ValueError, "input changed"):
            validate_pins(manifest)

    def test_standalone_task_text_does_not_require_a_campaign_helper(self):
        (self.library / "TASK.md").write_text("Implement the task.\n")
        task = SimpleNamespace(root=self.library, manifest={"language": "rust"})
        text = task_text(task, self.root / "toolchain")
        self.assertIn("Harness execution environment", text)
        self.assertNotIn("frozen campaign input", text)

    def test_real_sandbox_runs_archived_just_with_pinned_rust_tools(self):
        binary = os.environ.get("CODEX_LAB_TEST_BINARY")
        toolchain = os.environ.get("CODEX_LAB_TEST_RUST_TOOLCHAIN")
        original = os.environ.get("CODEX_LAB_TEST_JUST")
        if sys.platform != "linux" or not all((binary, toolchain, original)):
            self.skipTest("real helper check requires the sandbox, Rust toolchain, and just paths")
        toolchain = Path(toolchain).resolve(strict=True)
        original = Path(original).resolve(strict=True)
        sandbox = Path(binary).parent / "codex-linux-sandbox"
        archive = self.root / "inputs/lab"
        archive.mkdir(parents=True)
        helper = Path(archive_just(archive, original)["task_just"])
        source = Path(__file__).resolve().parents[1]
        task = load_task(source / "tasks/rust/rust_ranges")
        metadata = setup(self.root / "fixture", task, toolchain, helper)
        repository = Path(metadata["repository"])
        command = (repository / "TASK.md").read_text().split("```sh\n", 1)[1].split("\n```", 1)[0]
        scratch = self.root / "scratch"
        scratch.mkdir()
        reads = [repository, toolchain, helper.parent, sandbox, sandbox.resolve(),
                 sandbox.resolve().parent / "codex-resources"]
        entries = [{"path": {"type": "special", "value": {"kind": "minimal"}}, "access": "read"}]
        entries += [{"path": {"type": "path", "path": str(path)}, "access": "read"}
                    for path in reads if path.exists()]
        entries.append({"path": {"type": "path", "path": str(scratch)}, "access": "write"})
        profile = {"type": "managed", "network": "restricted",
                   "file_system": {"type": "restricted", "entries": entries}}
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                       "HOME": str(scratch), "TMPDIR": str(scratch),
                       "CARGO_HOME": str(scratch / "cargo-home"),
                       "CARGO_TARGET_DIR": str(scratch / "target"), "CARGO_BUILD_JOBS": "1"}
        result = subprocess.run(
            [str(sandbox), "--sandbox-policy-cwd", str(repository),
             "--permission-profile", json.dumps(profile), "--", "/bin/sh", "-c",
             f"test ! -r {shlex.quote(str(original))} && {command}"],
            cwd=repository, env=environment, text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("existing_overlap_and_empty_rules ... ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
