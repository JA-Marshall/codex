import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

CASES = [{'id': 'existing-good-and-mismatch', 'files': {'root/a.txt': 'hello', 'root/b.txt': 'world', 'manifest.json': '[{"id": "a", "path": "a.txt", "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"}, {"id": "b", "path": "b.txt", "sha256": "8810ad581e59f2bc3928b261707a71308f7e139eb04820366dc4d5c18d980225"}]'}, 'steps': [{'argv': ['root', 'manifest.json', 'report.json'], 'stdin': '', 'expect': {'exit': 0, 'stdout_json': {'ok': 1, 'mismatch': 1, 'error': 0}, 'files': {'report.json': '{"results":[{"actual":"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824","id":"a","status":"ok"},{"actual":"486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7","id":"b","status":"mismatch"}],"summary":{"error":0,"mismatch":1,"ok":1}}\n'}}}]}]
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
