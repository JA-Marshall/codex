import csv
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class PublicTest(unittest.TestCase):
    def test_comma_in_label(self):
        result = run({"rows": [{"sku": "a", "label": "red, large"}]})
        self.assertEqual(
            list(csv.reader(io.StringIO(result))),
            [["sku", "label"], ["a", "red, large"]],
        )
