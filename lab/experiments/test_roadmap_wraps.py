"""Replay actual development planner failures without provider calls."""

import copy
import json
from pathlib import Path
import unittest

from workflows.roadmap import propose, source_contains
from test_roadmap import context


class RoadmapWrapTest(unittest.TestCase):
    def test_actual_order_and_checkout_planner_artifacts_preserve_raw_scope(self):
        root = Path(__file__).with_name("fixtures") / "roadmap-wraps"
        for name, mismatches in [("order", 2), ("checkout", 4)]:
            with self.subTest(name=name):
                fixture = json.loads((root / (name + ".json")).read_text())
                plan = json.loads(fixture["response"])
                self.assertEqual(
                    sum(
                        item["source_quote"] not in fixture["intent"]
                        for item in plan["requirements"]
                    ),
                    mismatches,
                )
                roadmap = propose(fixture["intent"], fixture["response"])
                self.assertEqual(roadmap["source_intent"], fixture["intent"])
                self.assertEqual(roadmap["requirements"], plan["requirements"])
                self.assertEqual(roadmap["increments"], plan["increments"])
                self.assertEqual(roadmap["owner_followups"], [])
                changed = copy.deepcopy(plan)
                changed["requirements"][0]["source_quote"] += " and delete all history"
                with self.assertRaisesRegex(ValueError, "source-grounded"):
                    propose(fixture["intent"], json.dumps(changed))

    def test_only_single_line_endings_are_normalized(self):
        for source in [
            "sufficient\nstock must exist",
            "sufficient\r\nstock must exist",
        ]:
            self.assertTrue(source_contains(source, "sufficient stock must exist"))
        for source, quote in [
            ('Use ID "a  b".', 'Use ID "a b".'),
            ('Use ID "a\tb".', 'Use ID "a b".'),
            ("Charge 500 cents.", "Charge 5000 cents."),
            ("stock must exist", "stock may exist"),
            ('Use "pending".', 'Use "done".'),
            (
                "First paragraph.\n\nSecond paragraph.",
                "First paragraph. Second paragraph.",
            ),
            (
                "First paragraph.\r\n\r\nSecond paragraph.",
                "First paragraph. Second paragraph.",
            ),
        ]:
            with self.subTest(source=source, quote=quote):
                self.assertFalse(source_contains(source, quote))

    def test_space_or_tab_only_blank_lines_keep_paragraph_boundaries(self):
        for ending in ["\n", "\r\n"]:
            for blank in [" ", "\t", " \t "]:
                source = "First." + ending + blank + ending + "Second."
                flattened = "First. " + blank + " Second."
                with self.subTest(ending=ending, blank=blank):
                    self.assertFalse(source_contains(source, flattened))
                    self.assertFalse(source_contains(flattened, source))
                    self.assertTrue(source_contains(source, source))

    def test_explicit_followup_uses_same_wrap_policy_and_retains_prior_requirements(
        self,
    ):
        intent = "Preserve original IDs."
        plan = dict(
            **context(intent, "IDs remain unchanged."),
            open_questions=[],
            increments=[
                dict(
                    id="preserve",
                    intent=intent,
                    acceptance=["IDs remain unchanged."],
                    depends_on=[],
                    requirement_ids=["r-outcome"],
                )
            ],
        )
        original = propose(intent, json.dumps(plan))
        followup = "Charge 500 cents\r\nshipping."
        plan["requirements"].append(
            dict(
                id="r-shipping",
                source_quote="Charge 500 cents shipping.",
                acceptance=["Shipping costs 500 cents."],
            )
        )
        plan["increments"].append(
            dict(
                id="shipping",
                intent="Add shipping.",
                acceptance=["Shipping costs 500 cents."],
                depends_on=["preserve"],
                requirement_ids=["r-shipping"],
            )
        )
        revised = propose(
            intent,
            json.dumps(plan),
            previous=original,
            completed=["preserve"],
            owner_followup=followup,
            discovery="Owner requested shipping after the first increment.",
        )
        self.assertEqual(revised["owner_followups"], [followup])
        self.assertEqual(revised["requirements"][0], original["requirements"][0])
        plan["requirements"][-1]["source_quote"] = "Charge 50 cents shipping."
        with self.assertRaisesRegex(ValueError, "source-grounded"):
            propose(
                intent,
                json.dumps(plan),
                previous=original,
                completed=["preserve"],
                owner_followup=followup,
                discovery="Owner requested shipping after the first increment.",
            )


if __name__ == "__main__":
    unittest.main()
