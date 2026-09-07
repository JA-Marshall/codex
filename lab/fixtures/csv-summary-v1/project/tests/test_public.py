import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from csv_summary import summarize


class SummaryTests(unittest.TestCase):
    def test_repeated_categories(self):
        self.assertEqual(
            summarize("category,count\napples,2\npears,1\napples,3\n"),
            {"apples": 5, "pears": 1},
        )

    def test_quoted_comma(self):
        self.assertEqual(
            summarize('category,count\n"red, green",7\n'), {"red, green": 7}
        )

    def test_cli_result(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            source.write_text("category,count\npears,2\napples,1\n", encoding="utf-8")
            output = subprocess.run(
                [sys.executable, "cli.py", str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(
            (output.returncode, output.stdout),
            (0, json.dumps({"apples": 1, "pears": 2}, sort_keys=True) + "\n"),
        )


if __name__ == "__main__":
    unittest.main()
