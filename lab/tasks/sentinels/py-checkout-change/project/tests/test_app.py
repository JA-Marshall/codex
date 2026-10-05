import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class CheckoutTest(unittest.TestCase):
    def test_small_order(self):
        self.assertEqual(
            run(
                {
                    "items": [
                        {
                            "sku": "a",
                            "category": "goods",
                            "unit_price": 1000,
                            "quantity": 1,
                        }
                    ]
                }
            ),
            {"subtotal": 1000, "shipping": 500, "total": 1500},
        )
