import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class OrderTest(unittest.TestCase):
    def test_reserve_one(self):
        result = run(
            {
                "state": {"stock": {"a": 2}, "orders": {}},
                "operations": [
                    {"op": "reserve", "id": "one", "sku": "a", "quantity": 1}
                ],
            }
        )
        self.assertEqual(
            result["summary"], {"available": {"a": 1}, "reserved": {"a": 1}}
        )
