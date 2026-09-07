import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

CASES = [{'id': 'existing-releases', 'files': {}, 'steps': [{'argv': [], 'stdin': '["2.0.0","0.9.0","1.0.0"]', 'expect': {'exit': 0, 'stdout_json': ['0.9.0', '1.0.0', '2.0.0']}}]}]
MAIN = pathlib.Path(__file__).resolve().parents[1] / "src" / "main.py"


class PublicExamples(unittest.TestCase):
    def test_public_examples(self):
        for example in CASES:
            with self.subTest(example=example["id"]), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                for relative, content in example["files"].items():
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8", newline="")
                for action in example["steps"]:
                    result = subprocess.run([sys.executable, str(MAIN), *action["argv"]],
                                            input=action["stdin"], cwd=root, text=True,
                                            encoding="utf-8", capture_output=True, timeout=10)
                    expected = action["expect"]
                    self.assertEqual(result.returncode, expected["exit"], result.stderr)
                    self.assertEqual(json.loads(result.stdout), expected["stdout_json"])
                    for relative, content in expected.get("files", {}).items():
                        target = root / relative
                        if content is None:
                            self.assertFalse(target.exists())
                        else:
                            self.assertEqual(target.read_bytes(), content.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
