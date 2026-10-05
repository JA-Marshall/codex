"""Scope accounting must survive local commits, ignores, and control artifacts."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from workflows.bmad_install import BmadInstallation, inventory
from workflows.candidate import capture_product


class CandidateCaptureTest(unittest.TestCase):
    def test_committed_and_ignored_changes_stay_visible_and_controls_are_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            (workspace / "src").mkdir(parents=True)
            (workspace / "src/main.py").write_text("print('starter')\n")
            (workspace / ".gitignore").write_text("hidden.py\n_bmad-output/\n")
            starter = inventory(workspace)

            def git(*args):
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(workspace),
                        "-c",
                        "user.name=Fixture",
                        "-c",
                        "user.email=fixture@example.invalid",
                        *args,
                    ],
                    check=True,
                    capture_output=True,
                )

            git("init", "-q")
            git("add", ".")
            git("commit", "-qm", "Starter")
            (workspace / "src/main.py").write_text("print('implemented')\n")
            git("add", ".")
            git("commit", "-qm", "Implementation")
            (workspace / "hidden.py").write_text("unapproved = True\n")
            (workspace / "_bmad-output").mkdir()
            (workspace / "_bmad-output/spec.md").write_text("---\nstatus: done\n---\n")
            installed = BmadInstallation(
                workspace,
                {"protected": {}, "control_paths": ["_bmad-output"]},
                root / "unused",
            )
            runtime = {
                "process": {"stop_status": "confirmed"},
                "provider_handlers_stopped": True,
            }
            receipt = capture_product(
                workspace,
                root / "snapshot",
                starter=starter,
                write_paths=["src"],
                runtime=runtime,
                installation=installed,
            )
            self.assertEqual(receipt["changed_paths"], ["hidden.py", "src/main.py"])
            self.assertEqual(receipt["scope_violations"], ["hidden.py"])
            self.assertFalse((root / "snapshot/_bmad-output").exists())
            self.assertEqual(
                (root / "snapshot/src/main.py").read_text(), "print('implemented')\n"
            )
            runtime["process"]["stop_status"] = "unconfirmed"
            with self.assertRaisesRegex(ValueError, "shutdown"):
                capture_product(
                    workspace,
                    root / "unsafe",
                    starter=starter,
                    write_paths=["src"],
                    runtime=runtime,
                )
            self.assertFalse((root / "unsafe").exists())


if __name__ == "__main__":
    unittest.main()
