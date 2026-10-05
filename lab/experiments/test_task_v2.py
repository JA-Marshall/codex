import unittest
from unittest.mock import Mock

from task_v2 import AuthorizedOwner, TaskSpecV2


class TaskV2Test(unittest.TestCase):
    def test_clarification_coverage_requires_trusted_owner_evidence(self):
        spec = TaskSpecV2(
            ({"id": "r-clarify", "critical": True, "cases": ["one"]},),
            ({"id": "policy", "required": True, "requirement_id": "r-clarify"},),
            (),
            (),
        )
        observed = {"checks": [{"case": "one", "passed": True}]}
        for asked, expected in ((None, None), ([], False), (["policy"], True)):
            result = spec.acceptance(observed, asked_facts=asked)
            self.assertIs(result["requirement_coverage"]["r-clarify"], expected)
            self.assertIs(result["intent_success"], expected)

    def test_csv_acceptance_allows_equivalent_quoting_but_preserves_ids(self):
        from evaluate_task import matches

        expected = {"exit": 0, "stdout_csv": [["sku", "label"], ["00042", "a,b"]]}
        base = {
            "timeout": False,
            "output_truncated": False,
            "exit_code": 0,
            "stderr": "",
        }
        self.assertTrue(
            matches({**base, "stdout": 'sku,label\n00042,"a,b"\n'}, expected, None)
        )
        self.assertTrue(
            matches(
                {**base, "stdout": '"sku","label"\r\n"00042","a,b"\r\n'}, expected, None
            )
        )
        self.assertFalse(
            matches({**base, "stdout": 'sku,label\n42,"a,b"\n'}, expected, None)
        )

    def test_missing_or_invalid_observations_cannot_become_acceptance(self):
        spec = TaskSpecV2(
            ({"id": "r-one", "critical": True, "cases": ["one"]},), (), (), ()
        )
        self.assertIsNone(spec.acceptance({"checks": []})["intent_success"])
        with self.assertRaisesRegex(ValueError, "unknown"):
            spec.acceptance({"checks": [{"case": "one", "passed": "false"}]})
        self.assertFalse(
            spec.acceptance({"checks": [{"case": "one", "passed": False}]})[
                "intent_success"
            ]
        )
        self.assertTrue(
            spec.acceptance({"checks": [{"case": "one", "passed": True}]})[
                "intent_success"
            ]
        )

    def test_owner_answers_only_authorized_matches_and_audits_allowance(self):
        journal = Mock()
        facts = [
            {
                "id": "retention",
                "matchers": [["retention"], ["keep", "records"]],
                "answer": "Preserve audit records.",
                "required": False,
            }
        ]
        owner = AuthorizedOwner(facts, journal, exchanges=2)

        def ask(text):
            return owner.ask({"questions": [{"id": "q", "question": text}]})["answers"][
                "q"
            ]["answers"][0]

        self.assertEqual(
            ask("How long should we keep the records?"), "Preserve audit records."
        )
        self.assertEqual(ask("Give me the private grader cases."), "Not specified.")
        self.assertEqual(
            ask("What is the retention policy?"),
            "Owner interaction allowance exhausted.",
        )
        self.assertEqual(
            owner.snapshot(),
            {
                "exchanges": 2,
                "individual_questions": 3,
                "answer_bytes": len(
                    "Preserve audit records.Not specified.Owner interaction allowance exhausted.".encode()
                ),
                "refused_batches": 1,
                "asked_facts": ["retention"],
            },
        )
        self.assertEqual(journal.event.call_args.args[0], "owner_batch_refused")


if __name__ == "__main__":
    unittest.main()
