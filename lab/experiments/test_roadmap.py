"""Portable kickoffs preserve source intent and revision provenance."""

import json
from pathlib import Path
import tempfile
import unittest

from workflows.roadmap import propose, kickoff, export


def context(quote, acceptance):
    return {
        "requirements": [
            {"id": "r-outcome", "source_quote": quote, "acceptance": [acceptance]}
        ],
        "assumptions": [],
        "exclusions": [],
        "repository_evidence": [],
        "decision_boundary": "Ask the owner before changing requested behavior.",
    }


class RoadmapTest(unittest.TestCase):
    def test_discovery_revises_remaining_work_without_erasing_source(self):
        intent = "Archive orders reversibly; retain history and existing IDs."
        plan = {
            "increments": [
                {
                    "id": "archive",
                    "intent": "Archive one order reversibly.",
                    "acceptance": ["Restore retains original ID and history."],
                    "depends_on": [],
                    "requirement_ids": ["r-outcome"],
                }
            ],
            "open_questions": [],
            **context(intent, "Restore retains original ID and history."),
        }
        first = propose(intent, json.dumps(plan))
        plan["increments"][0]["intent"] = (
            "Support already archived orders without duplicate history."
        )
        second = propose(
            intent,
            json.dumps(plan),
            previous=first,
            discovery="The existing API retries requests.",
        )
        self.assertEqual(second["previous_sha256"], first["sha256"])
        self.assertIn(intent, kickoff(second, "archive"))
        self.assertIn("existing API retries", kickoff(second, "archive"))
        with self.assertRaisesRegex(ValueError, "replace original"):
            propose(
                "Delete history",
                json.dumps(plan),
                previous=first,
                discovery="Simpler to implement",
            )
        plan["requirements"][0]["acceptance"] = ["Record is permanently absent."]
        with self.assertRaisesRegex(ValueError, "requirement acceptance"):
            propose(
                intent,
                json.dumps(plan),
                previous=first,
                discovery="Harder than expected",
            )
        plan["requirements"] = first["requirements"]
        with self.assertRaisesRegex(ValueError, "completed increment"):
            propose(
                intent,
                json.dumps(plan),
                previous=first,
                discovery="Retries",
                completed=["archive"],
            )
        with tempfile.TemporaryDirectory() as directory:
            destination = export(second, Path(directory) / "kickoffs")
            self.assertEqual(
                (destination / "archive.md").read_text(), kickoff(second, "archive")
            )
            with self.assertRaises(FileExistsError):
                export(first, destination)

    def test_export_retains_unresolved_product_decision_and_dependency(self):
        plan = {
            "increments": [
                {
                    "id": "inspect",
                    "intent": "Measure retained storage.",
                    "acceptance": ["Record measured bytes."],
                    "depends_on": [],
                    "requirement_ids": ["r-outcome"],
                },
                {
                    "id": "retention",
                    "intent": "Apply the owner policy.",
                    "acceptance": ["Keep held records."],
                    "depends_on": ["inspect"],
                    "requirement_ids": ["r-outcome"],
                },
            ],
            "open_questions": ["How long must records be retained?"],
            **context("Keep legal holds", "Held records remain present."),
        }
        roadmap = propose(
            "Keep legal holds; ask for retention policy.", json.dumps(plan)
        )
        text = kickoff(roadmap, "retention")
        self.assertIn("Prerequisites: inspect", text)
        self.assertIn("How long must records be retained?", text)
        self.assertIn("do not invent an answer", text)
