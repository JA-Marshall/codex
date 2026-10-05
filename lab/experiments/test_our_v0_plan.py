"""Discovery replanning preserves completed work and the common repair allowance."""

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_roadmap import context
from workflows.our_v0 import OurV0, review_response


class OurV0PlanTest(unittest.TestCase):
    def test_discovery_replans_only_remaining_work_and_exports_both_revisions(self):
        plan = {
            **context("Keep history", "Restoring preserves original history."),
            "open_questions": [],
            "increments": [
                {
                    "id": "archive",
                    "intent": "Archive reversibly.",
                    "acceptance": ["Archived records remain stored."],
                    "depends_on": [],
                    "requirement_ids": ["r-outcome"],
                },
                {
                    "id": "restore",
                    "intent": "Restore records.",
                    "acceptance": ["Restored records retain history."],
                    "depends_on": ["archive"],
                    "requirement_ids": ["r-outcome"],
                },
            ],
        }
        revised = copy.deepcopy(plan)
        revised["increments"][1]["intent"] = (
            "Restore records idempotently when requests are retried."
        )
        discovery = {
            "findings": [],
            "discoveries": ["The existing client retries restore requests."],
        }
        texts = [
            json.dumps(plan),
            "built",
            json.dumps(discovery),
            json.dumps(revised),
            "built",
            json.dumps({"findings": [], "discoveries": []}),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            session = SimpleNamespace(
                workspace=temporary,
                new_thread=Mock(),
                turn=Mock(
                    side_effect=[
                        {"status": "completed", "text": text} for text in texts
                    ]
                ),
            )
            run = SimpleNamespace(session=session, artifacts=Path(temporary))
            with patch(
                "workflows.our_v0.subprocess.check_output", return_value="a" * 40
            ):
                result = OurV0(
                    run, Mock(side_effect=[{"passed": False}, {"passed": True}])
                ).invoke("Keep history")
            self.assertEqual(result["recipe_status"], "completed")
            self.assertEqual(result["completed"], ["archive", "restore"])
            first = json.loads((Path(temporary) / "roadmap-1/roadmap.json").read_text())
            second = json.loads(
                (Path(temporary) / "roadmap-2/roadmap.json").read_text()
            )
            self.assertEqual(second["requirements"], first["requirements"])
            self.assertEqual(second["increments"][0], first["increments"][0])
            self.assertEqual(second["completed"], ["archive"])
            self.assertNotEqual(
                result["increments"][0]["builder"], result["increments"][1]["builder"]
            )

    def test_unknown_requirement_cannot_become_a_review_finding(self):
        with self.assertRaisesRegex(ValueError, "original obligation"):
            review_response(
                json.dumps(
                    {
                        "findings": [
                            {
                                "requirement_id": "r-invented",
                                "evidence": "file.py:1",
                                "consequence": "New feature absent",
                                "smallest_fix": "Add it",
                            }
                        ],
                        "discoveries": [],
                    }
                ),
                {"r-outcome"},
            )
