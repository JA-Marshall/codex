import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import run


class PublicTest(unittest.TestCase):
    def test_archived_item_leaves_default_view(self):
        result = run(
            {
                "items": [{"id": "a", "active": True, "events": []}],
                "actions": [{"op": "archive", "id": "a"}],
            }
        )
        self.assertEqual(result["visible"], [])
