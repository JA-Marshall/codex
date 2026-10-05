"""Stock installer and renderer running inside the actual scored-trial boundary."""

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.bmad_install import BmadPackage, inventory
from workflows.evaluation import evaluate_stopped
from task_registry import (
    load_task,
    evaluator_fingerprint,
    inventory as task_inventory,
    task_text,
)
from workflows.bmad import BmadDispatch, spec_claim


class BmadInstallTest(SdkFixture):
    def test_planning_checkpoint_resumes_same_thread_and_budget(self):
        package = BmadPackage.from_lock(
            Path("/home/james/.cache/codex-lab-bmad/v6.12.0"),
            Path("/home/james/.local/share/codex-lab-toolchain/bin/uv"),
        )
        installed = package.install(self.workspace, self.root / "install-evidence")
        relative = "_bmad-output/spec-greeting.md"

        def status_response(status):
            content = f"---\nstatus: '{status}' # stock state\n---\nGreeting intent\n"
            command = "python3 -c " + shlex.quote(
                f"from pathlib import Path; Path({relative!r}).write_text({content!r})"
            )
            self.mock.enqueue_sse(
                sse(
                    [
                        ev_response_created(status),
                        ev_function_call(
                            status,
                            "exec_command",
                            json.dumps({"cmd": command, "yield_time_ms": 10000}),
                        ),
                        ev_completed(status),
                    ]
                )
            )
            self.response(status)

        status_response("ready-for-dev")
        run = self.start(sandbox=installed.sandbox())
        dispatch = BmadDispatch(run, installed)
        first = dispatch.invoke(
            "Add a greeting function.", halt_after_planning=True, spec=relative
        )
        self.assertEqual(first["spec_claim"]["status_claim"], "ready-for-dev")
        thread = run.bridge.parent_thread
        deadline = run.ledger.deadline
        count = len(self.mock.requests())
        status_response("done")
        second = dispatch.resume()
        self.assertEqual(second["spec_claim"]["status_claim"], "done")
        self.assertEqual(run.bridge.parent_thread, thread)
        self.assertEqual(run.ledger.deadline, deadline)
        self.assertGreater(len(self.mock.requests()), count)
        with self.assertRaisesRegex(ValueError, "new follow-up run"):
            dispatch.resume()
        self.assertEqual(run.close()["process"]["stop_status"], "confirmed")
        # Claims remain claims: no product acceptance is inferred from done.
        self.assertNotIn("task_success", second)
        (self.workspace / relative).write_text(
            "---\nstatus: blocked\n---\nNeed owner clarification\n"
        )
        dispatch.checkpoint = spec_claim(installed, relative)
        with self.assertRaisesRegex(ValueError, "owner resolution"):
            dispatch.resume()

    def test_actual_local_commit_is_independently_graded_after_shutdown(self):
        task = load_task(
            Path(__file__).resolve().parents[1] / "tasks/python/py-log-tally"
        )
        shutil.copytree(task.root / "project", self.workspace, dirs_exist_ok=True)
        (self.workspace / "TASK.md").write_text(task_text(task))
        starter, assets, evaluator = (
            inventory(self.workspace),
            task_inventory(task.root),
            evaluator_fingerprint(),
        )

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(self.workspace), *args], text=True
            ).strip()

        git("init", "-q")
        git("config", "user.name", "Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("add", ".")
        git("commit", "-qm", "Starter")
        baseline = git("rev-parse", "HEAD")
        package = BmadPackage.from_lock(
            Path("/home/james/.cache/codex-lab-bmad/v6.12.0"),
            Path("/home/james/.local/share/codex-lab-toolchain/bin/uv"),
        )
        installed = package.install(self.workspace, self.root / "install-evidence")
        # Scripted reference edits test execution/grading plumbing, never model quality.
        script = "from pathlib import Path\n"
        for path in sorted((task.root / "solution").rglob("*.py")):
            script += f"Path({path.relative_to(task.root / 'solution').as_posix()!r}).write_text({path.read_text()!r})\n"
        script += "import subprocess\nsubprocess.run(['git','add','src'],check=True)\nsubprocess.run(['git','commit','-m','Implement tally'],check=True)\nprint('PRODUCT_COMMITTED')\n"
        command = "python3 -c " + shlex.quote(script)
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("implement"),
                    ev_function_call(
                        "implement",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": command,
                                "yield_time_ms": 10000,
                                "max_output_tokens": 2000,
                            }
                        ),
                    ),
                    ev_completed("implement"),
                ]
            )
        )
        self.response("implementation finished")
        run = self.start(sandbox=installed.sandbox())
        run.parent(installed.kickoff("Implement the task in TASK.md."))
        alias = self.root / "codex-linux-sandbox"
        alias.symlink_to(self.pin.binary)
        result = evaluate_stopped(
            run,
            task,
            starter=starter,
            task_assets=assets,
            evaluator=evaluator,
            sandbox=alias,
            installation=installed,
        )
        self.assertNotEqual(git("rev-parse", "HEAD"), baseline)
        self.assertTrue(result["task_success"], result)
        self.assertEqual(result["scope_violations"], [])
        self.assertFalse((run.artifacts / "evaluation/candidate/_bmad").exists())

    def test_stock_install_and_immutable_renderer_work_inside_sdk_sandbox(self):
        package = BmadPackage.from_lock(
            Path("/home/james/.cache/codex-lab-bmad/v6.12.0"),
            Path("/home/james/.local/share/codex-lab-toolchain/bin/uv"),
        )
        installed = package.install(self.workspace, self.root / "install-evidence")
        command = " ".join(
            shlex.quote(part)
            for part in [
                "uv",
                "run",
                "--no-cache",
                str(self.workspace / "_bmad/scripts/render_skill.py"),
                "--project-root",
                str(self.workspace),
                "--skill",
                str(self.workspace / ".agents/skills/bmad-build-auto"),
            ]
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("render"),
                    ev_function_call(
                        "render",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": command,
                                "yield_time_ms": 10000,
                                "max_output_tokens": 2000,
                            }
                        ),
                    ),
                    ev_completed("render"),
                ]
            )
        )
        self.response("render complete")
        run = self.start(sandbox=installed.sandbox())
        run.parent(installed.kickoff("Add a greeting function."))
        outputs = [
            item.get("output", "")
            for request in self.mock.requests()
            for item in request.body_json()["input"]
            if item.get("type") == "function_call_output"
        ]
        self.assertIn(
            "read and follow " + installed.manifest["rendered"]["bmad-build-auto"],
            "\n".join(outputs),
        )
        self.assertEqual(run.close()["process"]["stop_status"], "confirmed")
        installed.verify()
        self.assertEqual(
            (self.workspace / "_bmad/LICENSE").read_bytes(),
            (package.source / "LICENSE").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
