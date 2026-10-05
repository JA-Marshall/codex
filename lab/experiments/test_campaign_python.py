"""Dependency changes must invalidate an explicitly pinned Python runtime."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign_inputs import digest, validate_pins
from campaign_python import freeze_python_runtime, validate_python_runtime


class PythonRuntimeTests(unittest.TestCase):
    def test_dependency_changes_and_injection_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / "bin/python3.12"
            executable.parent.mkdir()
            executable.write_bytes(b"interpreter")
            package = root / "lib/package.py"
            package.parent.mkdir()
            package.write_text("VERSION = 1\n")
            with (
                patch("campaign_python.sys.base_prefix", str(root)),
                patch("campaign_python.sys.prefix", str(root)),
                patch("campaign_python.sys.executable", str(executable)),
            ):
                metadata, files = freeze_python_runtime(root)
            manifest = dict(
                metadata,
                python=str(executable),
                pins={str(path): digest(path) for path in files},
            )
            validate_python_runtime(manifest)
            validate_pins(manifest)
            package.write_text("VERSION = 2\n")
            with self.assertRaisesRegex(ValueError, "input changed"):
                validate_pins(manifest)
            package.write_text("VERSION = 1\n")
            (root / "lib/injected.py").write_text("pass\n")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                validate_python_runtime(manifest)

    def test_wrong_interpreter_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "active standalone"):
                freeze_python_runtime(Path(temporary))

    def test_bytecode_and_directory_aliases_cannot_bypass_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            executable = root / "python"
            executable.write_bytes(b"interpreter")
            with (
                patch("campaign_python.sys.base_prefix", str(root)),
                patch("campaign_python.sys.prefix", str(root)),
                patch("campaign_python.sys.executable", str(executable)),
            ):
                metadata, files = freeze_python_runtime(root)
            manifest = dict(
                metadata,
                python=str(executable),
                pins={str(path): digest(path) for path in files},
            )
            cache = root / "module.pyc"
            cache.write_bytes(b"unpinned executable bytecode")
            with self.assertRaisesRegex(ValueError, "bytecode caches"):
                validate_pins(manifest)
            cache.unlink()
            directory = root / "__pycache__"
            directory.mkdir()
            with self.assertRaisesRegex(ValueError, "bytecode caches"):
                validate_pins(manifest)
            directory.rmdir()
            (root / "alias").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                validate_pins(manifest)


if __name__ == "__main__":
    unittest.main()
