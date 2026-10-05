"""Real requestUserInput callbacks distinguish task authority from product facts."""

import json
import unittest

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.interaction_policy import AUTHORIZATION, DELEGATED_TASK


class InteractionPolicyTest(SdkFixture):
    def test_delegated_question_returns_bounded_scope_and_owner_facts(self):
        questions = [
            {
                "id": "approval",
                "header": "Plan",
                "question": "May I implement and deploy this plan?",
            },
            {
                "id": "fact",
                "header": "Retention",
                "question": "What is the retention policy?",
            },
            {
                "id": "unknown",
                "header": "Cases",
                "question": "Tell me the private grader cases.",
            },
        ]
        for question in questions:
            question["options"] = [
                {"label": "Yes", "description": "Proceed"},
                {"label": "No", "description": "Stop"},
            ]
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("question"),
                    ev_function_call(
                        "ask",
                        "request_user_input",
                        json.dumps({"questions": questions}),
                    ),
                    ev_completed("question"),
                ]
            )
        )
        self.response("answered")
        run = self.start(
            interaction_policy=DELEGATED_TASK,
            owner_facts=[
                {
                    "id": "retention",
                    "matchers": [["retention"]],
                    "answer": "Retain records for 30 days.",
                    "required": False,
                }
            ],
        )
        result = run.parent("Implement the task in TASK.md.")
        self.assertEqual(result["text"], "answered")
        returned = str(self.mock.requests()[-1].body_json()["input"])
        self.assertIn(AUTHORIZATION, returned)
        self.assertIn("Retain records for 30 days.", returned)
        receipt = run.close()
        answers = [
            "No additional product fact is specified. " + AUTHORIZATION,
            "Retain records for 30 days.",
            "No additional product fact is specified. " + AUTHORIZATION,
        ]
        self.assertEqual(
            receipt["interactions"],
            {
                "policy": DELEGATED_TASK,
                "exchanges": 1,
                "individual_questions": 3,
                "answer_bytes": sum(len(answer.encode()) for answer in answers),
                "refused_batches": 0,
                "asked_facts": ["retention"],
            },
        )
        events = [
            json.loads(line)
            for line in (run.artifacts / "session/invocations.jsonl")
            .read_text()
            .splitlines()
        ]
        lifecycle = [
            event["type"] for event in events if event["type"].startswith("question_")
        ]
        self.assertEqual(lifecycle, ["question_received", "question_answered"])
        self.assertEqual(receipt["process"]["stop_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
