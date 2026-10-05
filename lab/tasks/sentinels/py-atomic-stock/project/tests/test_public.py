from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class PublicTest(unittest.TestCase):
    def test_valid_batch(self):
        result = run(
            {
                "stock": {"a": 5},
                "commands": [{"op": "batch", "changes": [{"sku": "a", "delta": -2}]}],
            }
        )
        self.assertEqual(result, {"stock": {"a": 3}, "results": [{"ok": True}]})
