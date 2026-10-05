"""Actual SDK increments receive changes only after stopped snapshot grading."""

import json
from pathlib import Path
import shlex
import time
from unittest.mock import patch

from test_sdk_workflows import SdkFixture, ROOT
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from provider_rate_limit import SharedLimiter
from task_registry import (
    load_task,
    setup,
    inventory as task_inventory,
    evaluator_fingerprint,
)
from workflows.bmad_install import inventory
from workflows.evaluation import evaluate_stopped
from workflows.evolving_project import EvolvingProject
from workflows.filesystem import SessionSandbox
from workflows.metered_run import MeteredRun
from workflows.usage import Budget
from workflows.trial_clock import TrialClock


class EvolvingProjectTest(SdkFixture):
    def test_campaign_worker_records_all_project_increments(self):
        import test_sdk_trial
        from workflows.sdk_trial import run_sdk_trial

        manifest = test_sdk_trial.SdkTrialTest.manifest(self)
        manifest["trials"][0]["fixture"] = "py-checkout-change"
        manifest["sdk_runtime"].update(
            task_directories={"py-checkout-change": "sentinels/py-checkout-change"},
            project_recipe="stop-probe-followup-v1",
            interaction_policy="delegated-task-v1",
        )
        task_root = ROOT / "lab/tasks/sentinels/py-checkout-change"
        for index, relative in enumerate(
            ("private/checkpoints/checkout-ready/src/app.py", "solution/src/app.py")
        ):
            script = (
                "from pathlib import Path; Path('src/app.py').write_text("
                + repr((task_root / relative).read_text())
                + ")"
            )
            self.mock.enqueue_sse(
                sse(
                    [
                        ev_response_created("write-" + str(index)),
                        ev_function_call(
                            "write-" + str(index),
                            "exec_command",
                            json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                        ),
                        ev_completed("write-" + str(index)),
                    ]
                )
            )
            self.response("submitted-" + str(index))
        with (
            patch("workflows.sdk_trial.check_service"),
            patch.dict("os.environ", {"SDK_TRIAL_TEST_KEY": "mock"}),
        ):
            result = run_sdk_trial(manifest, manifest["trials"][0])
        self.assertIs(result["task_success"], True, result)
        self.assertEqual(result["usage"]["requests"], 4)
        self.assertEqual(result["usage"]["run_id"], result["run_id"])
        evidence = result["workflow_result"]["evidence"]
        self.assertEqual(evidence["project"]["reached_milestones"], ["checkout-ready"])
        self.assertEqual(len(evidence["runtime"]["increment_runtime_receipts"]), 2)
        self.assertTrue(evidence["runtime"]["fidelity"]["complete"])

    def prepare_project(self, seconds=30, clock=None):
        task = load_task(ROOT / "lab/tasks/sentinels/py-checkout-change")
        metadata = setup(self.root / "fixture", task)
        self.workspace = Path(metadata["repository"])
        starter = inventory(self.workspace, exclude=(".git",))
        assets, evaluator = task_inventory(task.root), evaluator_fingerprint()
        alias = self.root / "codex-linux-sandbox"
        alias.symlink_to(self.pin.binary)
        project = EvolvingProject(
            task, Budget(8, 1000000, seconds), self.root / "project", clock=clock
        )
        created = []

        def make(index, budget, owner):
            run = MeteredRun(
                run_id="increment-" + str(index),
                pin=self.pin,
                workspace=self.workspace,
                artifacts=self.root / ("increment-" + str(index)),
                model="mock-model",
                budget=budget,
                shared_upstream=self.mock.url + "/v1",
                upstream_key="mock",
                limiter=SharedLimiter(startup_delay=0, window=0.1),
                sandbox=SessionSandbox(self.workspace),
                allow_workers=False,
                interaction_policy="delegated-task-v1",
                owner_state=owner,
                clock=clock,
            )
            created.append(run)
            self.addCleanup(run.close)
            return run

        def evaluate(run, reached):
            return evaluate_stopped(
                run,
                task,
                starter=starter,
                task_assets=assets,
                evaluator=evaluator,
                sandbox=alias,
                reached_milestones=reached,
            )

        return project, make, evaluate, created

    def test_real_submissions_deliver_change_and_conserve_budget(self):
        project, make, evaluate, created = self.prepare_project()
        for index, relative in enumerate(
            ("private/checkpoints/checkout-ready/src/app.py", "solution/src/app.py")
        ):
            source = (project.task.root / relative).read_text()
            script = (
                "from pathlib import Path; Path('src/app.py').write_text("
                + repr(source)
                + ")"
            )
            self.mock.enqueue_sse(
                sse(
                    [
                        ev_response_created("write-" + str(index)),
                        ev_function_call(
                            "write-" + str(index),
                            "exec_command",
                            json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                        ),
                        ev_completed("write-" + str(index)),
                    ]
                )
            )
            self.response("submitted-" + str(index))
        result = project.run(make, lambda run, prompt: run.parent(prompt), evaluate)
        self.assertEqual(result["reached_milestones"], ["checkout-ready"])
        self.assertIs(result["evaluation"]["task_success"], True)
        self.assertTrue(result["all_stopped"])
        self.assertEqual(result["requests"], 4)
        self.assertEqual([run.ledger.budget.requests for run in created], [8, 6])
        self.assertEqual(
            created[1].ledger.budget.tokens,
            1000000 - created[0].result["usage"]["charged_tokens"],
        )
        self.assertEqual(
            [run.ledger.deadline for run in created], [project.deadline] * 2
        )
        requests = self.mock.requests()
        self.assertNotIn("coupon", str(requests[0].body_json()["input"]))
        self.assertIn("coupon", str(requests[2].body_json()["input"]))
        self.assertNotIn("cross-threshold", str(requests[2].body_json()["input"]))
        self.assertNotEqual(
            result["increments"][0]["candidate_sha256"],
            result["increments"][1]["candidate_sha256"],
        )

    def test_setup_expiration_never_starts_a_model_request(self):
        project, make, evaluate, created = self.prepare_project()

        def slow_make(*args):
            run = make(*args)
            # Expire during setup deterministically, without racing admission.
            project.deadline = time.monotonic() - 0.001
            return run

        result = project.run(
            slow_make, lambda run, prompt: run.parent(prompt), evaluate
        )
        self.assertEqual(self.mock.requests(), [])
        self.assertEqual(result["requests"], 0)
        self.assertEqual(result["reached_milestones"], [])
        self.assertTrue(result["all_stopped"])
        self.assertIsNone(created[0].server_thread.ident)

    def test_human_clock_survives_long_grading_across_actual_increments(self):
        clock=TrialClock(30)
        project,make,evaluate,created=self.prepare_project(clock=clock)
        for index,relative in enumerate(('private/checkpoints/checkout-ready/src/app.py','solution/src/app.py')):
            source=(project.task.root/relative).read_text()
            script="from pathlib import Path; Path('src/app.py').write_text("+repr(source)+")"
            self.mock.enqueue_sse(sse([ev_response_created(f'human-write-{index}'),ev_function_call(f'human-write-{index}','exec_command',json.dumps({'cmd':'python3 -c '+shlex.quote(script)})),ev_completed(f'human-write-{index}')]))
            self.response(f'human-submitted-{index}')
        def setup(*args):
            self.assertEqual(clock.state,'setup')
            time.sleep(.05)
            return make(*args)
        def grade(run,reached):
            self.assertEqual(clock.state,'grading')
            if len(created)==1:
                # Longer than the discontinuity threshold, with no runtime
                # monitor alive. The trial-owned heartbeat must remain active.
                time.sleep(31)
            self.assertIsNone(clock.snapshot()['interruption'])
            return evaluate(run,reached)
        result=project.run(setup,lambda run,prompt:run.parent(prompt),grade)
        self.assertIs(result['evaluation']['task_success'],True)
        self.assertEqual(result['requests'],4)
        self.assertEqual([run.ledger.budget.requests for run in created],[8,6])
        self.assertEqual(created[1].ledger.budget.tokens,1000000-created[0].result['usage']['charged_tokens'])
        self.assertTrue(all(run.clock is run.session.clock is run.ledger.clock is project.clock for run in created))
        snapshot=clock.snapshot()
        self.assertEqual(snapshot['state'],'terminal')
        self.assertGreaterEqual(snapshot['elapsed']['grading'],31)
        self.assertGreater(snapshot['elapsed']['setup'],.1)
        self.assertLess(snapshot['agent_seconds'],30)
        self.assertIsNone(snapshot['interruption'])

    def test_unconfirmed_latest_increment_cannot_reuse_previous_grade(self):
        project, make, evaluate, created = self.prepare_project()
        for index in range(2):
            source = (project.task.root / "solution/src/app.py").read_text()
            script = (
                "from pathlib import Path; Path('src/app.py').write_text("
                + repr(source)
                + ")"
            )
            self.mock.enqueue_sse(
                sse(
                    [
                        ev_response_created("write-" + str(index)),
                        ev_function_call(
                            "write-" + str(index),
                            "exec_command",
                            json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                        ),
                        ev_completed("write-" + str(index)),
                    ]
                )
            )
            self.response("submitted-" + str(index))
        close = MeteredRun.close

        def uncertain_last(run):
            receipt = close(run)
            if run is created[-1] and len(created) == 2:
                return {
                    **receipt,
                    "process": {**receipt["process"], "stop_status": "unconfirmed"},
                }
            return receipt

        with patch.object(MeteredRun, "close", uncertain_last):
            result = project.run(make, lambda run, prompt: run.parent(prompt), evaluate)
        self.assertIsNone(result["evaluation"])
        self.assertFalse(result["all_stopped"])
        self.assertEqual(len(result["increments"]), 1)
        self.assertEqual(len(result["runtime_receipts"]), 2)
