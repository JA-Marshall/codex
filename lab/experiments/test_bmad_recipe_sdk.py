"""Actual SDK recipe stages and independently graded output, with mocked model IO."""

import json
from pathlib import Path
import shlex
from unittest.mock import patch

import test_sdk_trial
from test_sdk_workflows import SdkFixture, ROOT
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.sdk_trial import run_sdk_trial


class BmadRecipeSdkTest(SdkFixture):
    def test_second_recipe_failure_cannot_inherit_first_completion(self):
        manifest = test_sdk_trial.SdkTrialTest.manifest(self)
        manifest["trials"][0].update(
            fixture="py-checkout-change", workflow="bmad-orchestrated-v6.12.0-recipe1"
        )
        manifest["sdk_runtime"].update(
            task_directories={"py-checkout-change": "sentinels/py-checkout-change"},
            project_recipe="stop-probe-followup-v1",
            interaction_policy="delegated-task-v1",
            bmad_source="/home/james/.cache/codex-lab-bmad/v6.12.0",
            bmad_source_sha256=json.loads(
                (ROOT / "lab/bmad-method.lock.json").read_text()
            )["source_sha256"],
            uv="/home/james/.local/share/codex-lab-toolchain/bin/uv",
        )
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
        self.response("Initial implementation complete")
        calls = []

        def invoke(recipe, intent, slug):
            calls.append(slug)
            if len(calls) == 2:
                raise RuntimeError("injected second recipe failure")
            return {
                "turn": recipe.run.parent(intent),
                "recipe_status": "completed",
                "increments": [],
            }

        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
            patch("workflows.bmad_orchestrated.BmadOrchestrated.invoke", invoke),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        observed = result["workflow_result"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(observed["workflow_status"], "failed")
        self.assertEqual(observed["stop_status"], "confirmed")
        self.assertIsNone(observed["evidence"]["bmad_dispatch"])
        self.assertEqual(
            observed["evidence"]["turn_error"],
            {"message": "injected second recipe failure", "error_type": "RuntimeError"},
        )
        self.assertIs(result["task_success"], False)

    def test_headless_spec_planner_story_binding_and_final_private_grade(self):
        manifest = test_sdk_trial.SdkTrialTest.manifest(self)
        manifest["trials"][0]["workflow"] = "bmad-orchestrated-v6.12.0-recipe1"
        manifest["sdk_runtime"].update(
            bmad_source="/home/james/.cache/codex-lab-bmad/v6.12.0",
            bmad_source_sha256=json.loads(
                (ROOT / "lab/bmad-method.lock.json").read_text()
            )["source_sha256"],
            uv="/home/james/.local/share/codex-lab-toolchain/bin/uv",
            interaction_policy="delegated-task-v1",
        )
        folder = "_bmad-output/specs/spec-py-log-tally"
        spec_script = (
            "from pathlib import Path\n"
            + f"folder=Path({folder!r}); folder.mkdir(parents=True)\n"
            + "(folder/'SPEC.md').write_text('# Log tally\\nImplement TASK.md without changing its obligations.\\n')\n"
            + "(folder/'.memlog.md').write_text('direction: Implement TASK.md\\n')\n"
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("spec-write"),
                    ev_function_call(
                        "spec-write",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(spec_script)}),
                    ),
                    ev_completed("spec-write"),
                ]
            )
        )
        self.response(
            json.dumps(
                {
                    "status": "complete",
                    "files": [folder + "/SPEC.md", folder + "/.memlog.md"],
                }
            )
        )
        self.response(
            json.dumps(
                {
                    "increments": [
                        {
                            "id": "tally",
                            "intent": "Implement log tally from TASK.md.",
                            "acceptance": [
                                "CLI counts meet TASK.md and public tests pass"
                            ],
                            "depends_on": [],
                        }
                    ]
                }
            )
        )
        script = "from pathlib import Path\nimport json\n"
        source = ROOT / "lab/tasks/python/py-log-tally/solution"
        for path in sorted(source.rglob("*.py")):
            script += f"Path({path.relative_to(source).as_posix()!r}).write_text({path.read_text()!r})\n"
        script += (
            f"folder=Path({folder!r})\n"
            + "story=json.loads((folder/'stories.yaml').read_text())[-1]\n"
            + "(folder/'stories').mkdir(exist_ok=True)\n"
            + "(folder/'stories'/(story['id']+'-implementation.md')).write_text('---\\nstatus: done\\n---\\n')\n"
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("build"),
                    ev_function_call(
                        "build",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                    ),
                    ev_completed("build"),
                ]
            )
        )
        self.response("Implementation complete")
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertIs(result["task_success"], True, result)
        self.assertEqual(result["workflow_result"]["workflow_status"], "completed")
        recipe = result["workflow_result"]["evidence"]["bmad_dispatch"]
        self.assertEqual(recipe["recipe_status"], "completed")
        self.assertEqual(recipe["increments"][0]["spec_claim"]["status_claim"], "done")
        self.assertEqual(len(self.mock.requests()), 5)
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed")
