"""Actual SDK plus host public checks and external private grading, mocked model IO."""

import json
import shlex
import shutil
import time
from types import SimpleNamespace
from unittest.mock import patch

from test_sdk_workflows import SdkFixture, ROOT
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
import test_sdk_trial
from test_roadmap import context
from workflows.sdk_trial import run_sdk_trial
from workflows.public_verification import PublicVerifier
from task_registry import load_task


class OurV0Test(SdkFixture):
    def test_project_followup_cannot_reset_two_repairs_used_by_initial_increment(self):
        manifest = self.manifest()
        manifest["trials"][0]["fixture"] = "py-checkout-change"
        manifest["sdk_runtime"].update(
            task_directories={"py-checkout-change": "sentinels/py-checkout-change"},
            project_recipe="stop-probe-followup-v1",
            interaction_policy="delegated-task-v1",
        )
        manifest["sdk_runtime"]["budget"]["requests"] = 20
        plan = {
            **context(
                "Implement checkout totals", "Preserve the requested checkout behavior."
            ),
            "increments": [
                {
                    "id": "checkout",
                    "intent": "Implement the current checkout request.",
                    "acceptance": ["Current request and visible tests pass."],
                    "depends_on": [],
                    "requirement_ids": ["r-outcome"],
                }
            ],
            "open_questions": [],
        }
        self.response(json.dumps(plan))
        for _ in range(2):
            self.response("Implemented")
            self.response(json.dumps({"findings": [], "discoveries": []}))
        source = (
            ROOT
            / "lab/tasks/sentinels/py-checkout-change/private/checkpoints/checkout-ready/src/app.py"
        ).read_text()
        script = (
            "from pathlib import Path; Path('src/app.py').write_text("
            + repr(source)
            + ")"
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("initial"),
                    ev_function_call(
                        "initial",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                    ),
                    ev_completed("initial"),
                ]
            )
        )
        self.response("Initial checkout ready")
        self.response(json.dumps({"findings": [], "discoveries": []}))
        self.response(json.dumps(plan))
        self.response("Follow-up complete")
        self.response(
            json.dumps(
                {
                    "findings": [
                        {
                            "requirement_id": "r-outcome",
                            "evidence": "src/app.py ignores the new discount input",
                            "consequence": "Follow-up coupon totals remain incorrect",
                            "smallest_fix": "Apply the supplied discount rules",
                        }
                    ],
                    "discoveries": [],
                }
            )
        )
        result = self.execute(manifest)
        evidence = result["workflow_result"]["evidence"]
        self.assertEqual(evidence["project"]["admitted_increments"], 2)
        self.assertEqual(evidence["our_dispatch"]["repairs"], 2)
        self.assertEqual(len(evidence["our_dispatch"]["increments"][0]["attempts"]), 1)
        self.assertEqual(result["workflow_result"]["workflow_status"], "failed")
        self.assertIs(result["task_success"], False)
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed")
        self.assertEqual(len(self.mock.requests()), 11)

    def test_public_verifier_retains_failing_added_tests_and_identifies_checked_input(
        self,
    ):
        task = load_task(ROOT / "lab/tasks/python/py-log-tally")
        shutil.copytree(task.root / "project", self.workspace, dirs_exist_ok=True)
        shutil.copytree(task.root / "solution", self.workspace, dirs_exist_ok=True)
        (self.workspace / "tests/test_public.py").write_text(
            "# weakened original tests\n"
        )
        (self.workspace / "tests/test_regression.py").write_text(
            "import unittest\nclass Regression(unittest.TestCase):\n def test_new_obligation(self): self.assertEqual(1, 2)\n"
        )
        alias = self.root / "codex-linux-sandbox"
        alias.symlink_to(self.pin.binary)
        run = SimpleNamespace(
            session=SimpleNamespace(workspace=str(self.workspace)),
            ledger=SimpleNamespace(deadline=time.monotonic() + 30),
        )
        result = PublicVerifier(task, alias)(run)
        self.assertIs(result["passed"], False)
        self.assertIn("test_new_obligation", result["checks"][-1]["stderr"])
        self.assertNotEqual(
            result["captured_product_sha256"], result["check_input_sha256"]
        )

    def plan(self):
        return {
            **context(
                "Build a word-frequency CLI", "CLI preserves all TASK.md examples."
            ),
            "increments": [
                {
                    "id": "tally",
                    "intent": "Implement the complete word-frequency CLI.",
                    "acceptance": ["Public tests and TASK.md examples pass."],
                    "depends_on": [],
                    "requirement_ids": ["r-outcome"],
                }
            ],
            "open_questions": [],
        }

    def manifest(self):
        manifest = test_sdk_trial.SdkTrialTest.manifest(self)
        manifest["trials"][0]["workflow"] = "our-v0"
        manifest["sdk_runtime"]["budget"]["seconds"] = 60
        return manifest

    def execute(self, manifest):
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
        ):
            return run_sdk_trial(manifest, manifest["trials"][0])

    def test_public_failure_forces_same_builder_repair_despite_empty_review(self):
        manifest = self.manifest()
        self.response(json.dumps(self.plan()))
        self.response("Implementation complete")
        self.response(json.dumps({"findings": [], "discoveries": []}))
        source = ROOT / "lab/tasks/python/py-log-tally/solution"
        script = "from pathlib import Path\n"
        for path in sorted(source.rglob("*.py")):
            script += f"Path({path.relative_to(source).as_posix()!r}).write_text({path.read_text()!r})\n"
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("repair"),
                    ev_function_call(
                        "repair",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                    ),
                    ev_completed("repair"),
                ]
            )
        )
        self.response("Repaired and verified")
        self.response(json.dumps({"findings": [], "discoveries": []}))
        result = self.execute(manifest)
        observed = result["workflow_result"]
        recipe = observed["evidence"]["our_dispatch"]
        self.assertIs(result["task_success"], True, result)
        self.assertEqual(observed["workflow_status"], "completed")
        self.assertEqual(observed["stop_status"], "confirmed")
        self.assertEqual(recipe["repairs"], 1)
        attempts = recipe["increments"][0]["attempts"]
        self.assertEqual(
            [attempt["public"]["passed"] for attempt in attempts], [False, True]
        )
        self.assertEqual(len({attempt["reviewer"] for attempt in attempts}), 2)
        self.assertEqual(len(self.mock.requests()), 6)
        events = [
            json.loads(line)
            for line in (
                self.root / "campaign/runs/trial-0001/session/invocations.jsonl"
            )
            .read_text()
            .splitlines()
        ]
        builder = recipe["increments"][0]["builder"]
        turns = [
            event
            for event in events
            if event.get("type") == "turn_prompt" and event.get("worker_id") == builder
        ]
        self.assertEqual(len(turns), 2)
        self.assertEqual(len({event["thread_id"] for event in turns}), 1)

    def test_two_repairs_are_a_run_limit_and_cannot_turn_public_failure_into_success(
        self,
    ):
        manifest = self.manifest()
        self.response(json.dumps(self.plan()))
        for _ in range(3):
            self.response("Everything is correct")
            self.response(json.dumps({"findings": [], "discoveries": []}))
        result = self.execute(manifest)
        recipe = result["workflow_result"]["evidence"]["our_dispatch"]
        self.assertEqual(recipe["repairs"], 2)
        self.assertEqual(len(recipe["increments"][0]["attempts"]), 3)
        self.assertEqual(result["workflow_result"]["workflow_status"], "failed")
        self.assertIs(result["task_success"], False)
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed")
        self.assertEqual(len(self.mock.requests()), 7)
