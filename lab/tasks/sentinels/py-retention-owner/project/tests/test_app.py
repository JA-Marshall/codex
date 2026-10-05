import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class RetentionTest(unittest.TestCase):
    def test_recent_record_survives(self):
        records = [{"id": "00042", "created_day": 99, "note": "keep"}]
        self.assertEqual(run({"now_day": 100, "records": records}), records)
