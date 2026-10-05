"""Frozen worker records keep model completion distinct from acceptance/errors."""

from dataclasses import asdict
import json
import shlex
import subprocess
from pathlib import Path
from unittest.mock import patch
import unittest

from test_sdk_workflows import SdkFixture, ROOT
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.metered_run import MeteredRun
from workflows.sdk_trial import run_sdk_trial


class SdkTrialTest(SdkFixture):
    def test_required_owner_answer_reaches_stopped_product_grading(self):
        manifest = self.manifest()
        manifest["trials"][0]["fixture"] = "py-retention-owner"
        manifest["sdk_runtime"].update(
            interaction_policy="delegated-task-v1",
            task_directories={"py-retention-owner": "sentinels/py-retention-owner"},
        )
        question = {
            "questions": [
                {
                    "id": "retention",
                    "header": "Policy",
                    "question": "What is the retention policy?",
                    "options": [
                        {"label": "Thirty days", "description": "Short retention"},
                        {"label": "Forever", "description": "Keep all records"},
                    ],
                }
            ]
        }
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("ask"),
                    ev_function_call("ask", "request_user_input", json.dumps(question)),
                    ev_completed("ask"),
                ]
            )
        )
        source = (
            ROOT / "lab/tasks/sentinels/py-retention-owner/solution/src/app.py"
        ).read_text()
        script = (
            "from pathlib import Path; Path('src/app.py').write_text("
            + repr(source)
            + ")"
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("write"),
                    ev_function_call(
                        "write",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                    ),
                    ev_completed("write"),
                ]
            )
        )
        self.response("done")
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertIs(result["task_success"], True, result)
        evaluated = json.loads(
            (Path(manifest["output"]) / "trials/trial-0001/evaluation.json").read_text()
        )
        self.assertIs(evaluated["requirement_coverage"]["r-clarify"], True)
        self.assertIs(evaluated["delivery_success"], True)
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed")

    def test_failure_before_model_dispatch_retains_known_zero_usage(self):
        manifest = self.manifest()
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
            patch.object(
                MeteredRun, "parent", side_effect=RuntimeError("pre-dispatch failure")
            ),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertEqual(
            [
                result["usage"][name]
                for name in (
                    "requests",
                    "input_tokens",
                    "output_tokens",
                    "cached_input_tokens",
                )
            ],
            [0, 0, 0, 0],
        )
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed")

    def test_reporting_failure_still_grades_the_stopped_correct_product(self):
        manifest = self.manifest()
        manifest["trials"][0]["workflow"] = "bmad-build-auto-v6.12.0"
        manifest["sdk_runtime"].update(
            bmad_source="/home/james/.cache/codex-lab-bmad/v6.12.0",
            bmad_source_sha256=json.loads(
                (ROOT / "lab/bmad-method.lock.json").read_text()
            )["source_sha256"],
            uv="/home/james/.local/share/codex-lab-toolchain/bin/uv",
        )
        task_root = ROOT / "lab/tasks/python/py-log-tally"
        script = "from pathlib import Path\n"
        for path in sorted((task_root / "solution").rglob("*.py")):
            script += f"Path({path.relative_to(task_root / 'solution').as_posix()!r}).write_text({path.read_text()!r})\n"
        script += "import subprocess\nsubprocess.run(['git','add','src'],check=True)\nsubprocess.run(['git','commit','-m','Implement task'],check=True)\n"
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("write"),
                    ev_function_call(
                        "write",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": "python3 -c " + shlex.quote(script),
                                "yield_time_ms": 10000,
                            }
                        ),
                    ),
                    ev_completed("write"),
                ]
            )
        )
        self.response("done")
        original = MeteredRun.parent

        def reporting_failure(run, prompt):
            original(run, prompt)
            raise RuntimeError("injected dispatch reporting failure")

        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
            patch.object(MeteredRun, "parent", reporting_failure),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertEqual(result["workflow_result"]["workflow_status"], "failed", result)
        self.assertEqual(
            result["workflow_result"]["evaluation_status"], "completed", result
        )
        self.assertIs(result["task_success"], True, result)
        self.assertIn("reporting failure", result["workflow_error"])
        fixture = Path(manifest["output"]) / "trials/trial-0001/fixture"
        metadata = json.loads((fixture / "fixture.json").read_text())
        current = subprocess.check_output(
            ["git", "-C", metadata["repository"], "rev-parse", "HEAD"], text=True
        ).strip()
        self.assertNotEqual(current, metadata["commit"])

    def manifest(self):
        output = self.root / "campaign"
        (output / "trials/trial-0001").mkdir(parents=True)
        (output / "runs").mkdir()
        entry = {
            "run_id": "trial-0001",
            "fixture": "py-log-tally",
            "workflow": "direct-v1",
            "repetition": 1,
        }
        alias = self.root / "codex-linux-sandbox"
        alias.symlink_to(self.pin.binary)
        return {
            "schema_version": 1,
            "campaign_id": "offline-worker-probe",
            "output": str(output),
            "requested_model": "mock-model",
            "trials": [entry],
            "pins": {},
            "sandbox": str(alias),
            "task_root": str(ROOT / "lab/tasks"),
            "provider_service": {"base_url": self.mock.url + "/v1"},
            "sdk_runtime": {
                "sdk_source": str(ROOT / "sdk/python/src"),
                "pin": asdict(self.pin),
                "budget": {"requests": 8, "tokens": 1000000, "seconds": 30},
                "service_key_env": "SDK_TRIAL_TEST_KEY",
                "task_directories": {"py-log-tally": "python/py-log-tally"},
            },
        }

    def test_completed_turn_does_not_make_an_unimplemented_product_pass(self):
        manifest = self.manifest()
        self.response("Everything is correct and done.")
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertEqual(
            result["workflow_result"]["workflow_status"], "completed", result
        )
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed", result)
        self.assertEqual(
            result["workflow_result"]["evaluation_status"], "completed", result
        )
        self.assertIs(result["task_success"], False, result)
        self.assertEqual(result["usage"]["input_tokens"], 1)
        self.assertEqual(result["usage"]["output_tokens"], 1)
        tools = self.mock.requests()[0].body_json()["tools"]
        self.assertNotIn("run_workers", str(tools))
        self.assertNotIn("continue_worker", str(tools))

    def test_grader_exception_preserves_failed_result_with_unknown_acceptance(self):
        manifest = self.manifest()
        self.response("done")
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
            patch(
                "workflows.evaluation.grade",
                side_effect=RuntimeError("injected grader failure"),
            ),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        stored = json.loads(
            (Path(manifest["output"]) / "trials/trial-0001/result.json").read_text()
        )
        self.assertEqual(stored, result)
        self.assertIsNone(stored["task_success"])
        self.assertEqual(
            stored["workflow_result"]["evaluation_status"], "failed", stored
        )
        self.assertEqual(stored["workflow_result"]["stop_status"], "confirmed", stored)
        self.assertEqual(stored["evaluation_exit_code"], 1)
        failure = Path(manifest["output"]) / "runs/trial-0001/evaluation/failure.json"
        self.assertIsNone(json.loads(failure.read_text())["task_success"])


if __name__ == "__main__":
    unittest.main()
