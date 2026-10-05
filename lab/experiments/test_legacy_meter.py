"""Actual legacy host behind aggregate admission and the owned process boundary."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_sdk_workflows
from app_server_harness import (
    MockResponsesServer,
    sse,
    ev_response_created,
    ev_completed,
    ev_assistant_message,
    ev_function_call,
)
from campaign_inputs import digest
from run_campaign import run_logged, run_trial
from workflows.legacy_meter import LegacyPin
from workflows.session_process import SessionProcess

ROOT = Path(__file__).resolve().parents[2]


class LegacyMeterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="legacy-meter-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mock = MockResponsesServer().__enter__()
        self.addCleanup(self.mock.__exit__, None, None, None)
        self.output = self.root / "campaign"
        archive = self.output / "inputs/lab"
        archive.mkdir(parents=True)
        shutil.copytree(ROOT / "lab/instructions", archive / "instructions")
        # Evaluator modules are trusted host-only files, absent from the model mount.
        shutil.copytree(
            ROOT / "lab/experiments",
            archive / "experiments",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copyfile(
            ROOT / "lab/workflows/repository-v2.toml", archive / "workflow.toml"
        )
        for name in ("trials", "runs"):
            (self.output / name).mkdir()
        (self.output / "trials/trial-0001").mkdir()
        self.home = self.root / "original-profile"
        self.home.mkdir()
        self.secret = self.home / "upstream-credential-canary.txt"
        self.secret.write_text("private-upstream-marker")
        self.model = "lab-fixture-v1"
        model = dict(
            slug=self.model,
            display_name="Lab fixture",
            description=None,
            supported_reasoning_levels=[],
            shell_type="unified_exec",
            visibility="list",
            supported_in_api=True,
            priority=0,
            availability_nux=None,
            upgrade=None,
            support_verbosity=False,
            default_verbosity=None,
            apply_patch_tool_type="freeform",
            truncation_policy={"mode": "bytes", "limit": 8192},
            context_window=32768,
            experimental_supported_tools=[],
            include_apps_usage_instructions=False,
            tool_mode="direct",
            model_messages=dict(
                instructions_template="Follow the supplied workflow instructions.",
                instructions_variables=None,
                approvals=None,
                collaboration_modes=None,
                auto_review=None,
                permissions=None,
                multi_agent=None,
            ),
        )
        (self.home / "catalog.json").write_text(json.dumps({"models": [model]}))
        self.upstream = self.mock.url.rstrip("/") + "/v1"
        (self.home / "config.toml").write_text(
            f'model="{self.model}"\nmodel_provider="mock"\nmodel_catalog_json="catalog.json"\n[model_providers.mock]\nname="Mock"\nbase_url="{self.upstream}"\nwire_api="responses"\nenv_key="TEST_UPSTREAM_KEY"\nrequest_max_retries=0\nstream_max_retries=0\nstream_idle_timeout_ms=5000\n'
        )
        self.entry = dict(
            run_id="trial-0001",
            fixture="py-archive-intent",
            workflow="repository-v2",
            repetition=1,
        )
        self.manifest = dict(
            schema_version=1,
            campaign_id="legacy-meter-test",
            output=str(self.output),
            archive=str(archive),
            binary=os.environ["CODEX_LAB_TEST_BINARY"],
            sandbox=os.environ["CODEX_STUDY_TEST_BINARY"],
            codex_home=str(self.home),
            requested_model=self.model,
            catalog=str(archive / "workflow.toml"),
            python=sys.executable,
            task_root=str(ROOT / "lab/tasks/sentinels"),
            task_ids=["py-archive-intent"],
            provider_service={"base_url": self.upstream},
            max_amendments=0,
            pins={},
            trials=[self.entry],
            legacy_runtime={
                "budget": dict(
                    requests=10,
                    tokens=2000000,
                    seconds=40,
                    input_ceiling=200000,
                    output_ceiling=16000,
                )
            },
        )

    def response(self, identity, text=None, tool=None, arguments=None):
        item = (
            ev_function_call(identity, tool, json.dumps(arguments))
            if tool
            else ev_assistant_message(identity, text)
        )
        self.mock.enqueue_sse(
            sse([ev_response_created(identity), item, ev_completed(identity)])
        )

    def queue_workflow(self):
        self.response(
            "research",
            "Inspect the public source and implement the approved scope probe.",
        )
        plan = dict(
            schema_version=1,
            plan_id="task-plan",
            revision=1,
            goal="Verify bounded host isolation",
            assumptions=[],
            steps=[
                dict(
                    id="S01",
                    title="Probe isolation",
                    instructions="Run the scope probe and record src/probe.txt.",
                    affected_files=["src/probe.txt"],
                    depends_on=[],
                    acceptance_criteria=["AC01"],
                    verification=["V01"],
                )
            ],
            risks=[],
            acceptance_criteria=[
                dict(id="AC01", description="The scope probe passes.")
            ],
            verification_strategy=[
                dict(id="V01", description="Check src/probe.txt equals scope-probe-ok.")
            ],
            discoveries=[],
            blockers=[],
        )
        self.response("plan", json.dumps(plan))
        secret = str(self.secret)
        private = str(ROOT / "lab/tasks/sentinels/py-archive-intent/private/cases.json")
        port = int(self.upstream.split(":")[-1].split("/")[0])
        code = 'import os,socket\nfrom pathlib import Path\nassert not os.environ.get("TEST_UPSTREAM_KEY")\n'
        code += f'for name in {[secret, private, "/proc/self/root" + secret]!r}:\n try: Path(name).read_bytes()\n except (OSError,PermissionError): pass\n else: raise AssertionError("private read escaped")\n'
        code += f'try: connection=socket.create_connection(("127.0.0.1",{port}),timeout=.5)\nexcept OSError: pass\nelse: connection.close(); raise AssertionError("network bypass")\n'
        code += 'Path("src/probe.txt").write_text("scope-probe-ok")\nprint("scope-probe-ok")\n'
        command = (
            str(Path(sys.executable).resolve())
            + " -c "
            + "'"
            + code.replace("'", "'\"'\"'")
            + "'"
        )
        self.response(
            "implementation-probe",
            tool="exec_command",
            arguments=dict(cmd=command, timeout_ms=10000, max_output_tokens=1024),
        )
        self.response("implementation-done", json.dumps({"completed_steps": ["S01"]}))
        self.response(
            "verify",
            tool="exec_command",
            arguments=dict(
                cmd='test "$(cat src/probe.txt)" = scope-probe-ok',
                timeout_ms=5000,
                max_output_tokens=1024,
            ),
        )
        self.response("receipt", tool="lab_command_receipt", arguments={"index": 1})
        self.response(
            "verified",
            json.dumps(
                {
                    "checks": [
                        {
                            "verification_id": "V01",
                            "call_id": "verify",
                            "acceptance_criteria": ["AC01"],
                        }
                    ]
                }
            ),
        )

    def test_actual_legacy_phases_share_meter_and_cannot_read_private_or_bypass_network(
        self,
    ):
        self.queue_workflow()
        with (
            patch("run_campaign.check_service"),
            patch.dict(os.environ, {"TEST_UPSTREAM_KEY": "host-only-secret"}),
        ):
            result = run_trial(self.manifest, self.entry)
        diagnostic_paths = [
            self.output / "trials/trial-0001/host.stderr.log",
            self.output
            / "trials/trial-0001/legacy-meter/runs/trial-0001/evidence/failure.json",
        ]
        diagnostic = "\n".join(
            path.read_text()[-3000:] for path in diagnostic_paths if path.exists()
        )
        meter_path = self.output / "trials/trial-0001/legacy-meter/result.json"
        self.assertTrue(meter_path.exists(), diagnostic)
        meter = json.loads(meter_path.read_text())
        self.assertTrue(meter["namespace_stopped"], diagnostic)
        self.assertTrue(meter["provider_handlers_stopped"], diagnostic)
        self.assertEqual(meter["usage"]["requests"], 7, diagnostic)
        self.assertEqual(meter["usage"]["unknown_requests"], 0, diagnostic)
        self.assertEqual(
            (
                self.output / "trials/trial-0001/fixture/repository/src/probe.txt"
            ).read_text(),
            "scope-probe-ok",
        )
        self.assertEqual(result["legacy_meter_sha256"], digest(meter_path))
        self.assertEqual(
            result["workflow_result"]["workflow_status"], "completed", diagnostic
        )
        requests = self.mock.requests()
        self.assertEqual(len(requests), 7)
        for request in requests:
            self.assertEqual(request.header("authorization"), "Bearer host-only-secret")
            self.assertIsNone(request.header("x-lab-worker"))

    def test_request_budget_is_shared_across_original_phases(self):
        self.manifest["legacy_runtime"]["budget"]["requests"] = 3
        self.queue_workflow()
        with (
            patch("run_campaign.check_service"),
            patch.dict(os.environ, {"TEST_UPSTREAM_KEY": "host-only-secret"}),
        ):
            result = run_trial(self.manifest, self.entry)
        meter = json.loads(
            (self.output / "trials/trial-0001/legacy-meter/result.json").read_text()
        )
        self.assertEqual(len(self.mock.requests()), 3)
        self.assertEqual(meter["usage"]["requests"], 3)
        self.assertEqual(meter["usage"]["unknown_requests"], 0)
        self.assertTrue(meter["namespace_stopped"])
        self.assertTrue(meter["provider_handlers_stopped"])
        self.assertNotEqual(result["workflow_result"]["workflow_status"], "completed")

    def test_deadline_kills_detached_descendant_holding_capture_pipes(self):
        heartbeat = self.root / "heartbeat"
        child = self.root / "child.py"
        child.write_text(
            "import time\nfrom pathlib import Path\nwhile True:\n Path("
            + repr(str(heartbeat))
            + ").write_text(str(time.time()))\n time.sleep(.02)\n"
        )
        parent = self.root / "parent.py"
        parent.write_text(
            "import subprocess,sys,time\nsubprocess.Popen([sys.executable,"
            + repr(str(child))
            + "],start_new_session=True)\ntime.sleep(120)\n"
        )
        binary = str(Path(sys.executable).resolve())
        process = SessionProcess(
            LegacyPin.capture(binary),
            self.root / "deadline-home",
            self.root / "deadline-namespace.json",
        )
        start = time.monotonic()
        returncode = run_logged(
            process.launch_args(command=[binary, str(parent)]),
            self.root / "deadline",
            deadline=start + 2,
        )
        self.assertNotEqual(returncode, 0)
        self.assertLess(time.monotonic() - start, 10)
        self.assertTrue(process.stopped())
        self.assertTrue(heartbeat.exists())
        final = heartbeat.read_text()
        time.sleep(0.2)
        self.assertEqual(heartbeat.read_text(), final)


if __name__ == "__main__":
    unittest.main()
