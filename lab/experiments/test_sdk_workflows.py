"""Actual checkout SDK + local app-server + loopback Responses integration."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import tempfile
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk/python/src"))
sys.path.insert(0, str(ROOT / "sdk/python/tests"))

from app_server_harness import (
    MockResponsesServer,
    sse,
    ev_response_created,
    ev_completed,
    ev_assistant_message,
    ev_function_call,
)
from provider_rate_limit import SharedLimiter
from workflows.metered_run import MeteredRun
from workflows.session_process import RuntimePin, SessionProcess
from workflows.usage import Budget


class SdkFixture(unittest.TestCase):
    temporary_parent = None

    @classmethod
    def setUpClass(cls):
        binary = os.environ["CODEX_STUDY_TEST_BINARY"]
        cls.pin = RuntimePin.capture(binary, "db0f5c188a1b37959b92c7d0f5f35f52aff9175e")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="sdk-study-", dir=self.temporary_parent
        )
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.mock = MockResponsesServer().__enter__()
        self.addCleanup(self.mock.__exit__, None, None, None)
        self.run = None

    def start(
        self,
        requests=20,
        seconds=30,
        tokens=10000000,
        sandbox=None,
        interaction_policy=None,
        owner_facts=(),
        clock=None,
    ):
        self.run = MeteredRun(
            run_id="test-run",
            pin=self.pin,
            workspace=self.workspace,
            artifacts=self.root / "run",
            model="mock-model",
            budget=Budget(requests, tokens, seconds),
            shared_upstream=self.mock.url + "/v1",
            upstream_key="mock",
            limiter=SharedLimiter(startup_delay=0, window=0.1),
            sandbox=sandbox,
            interaction_policy=interaction_policy,
            owner_facts=owner_facts,
            clock=clock,
        )
        self.addCleanup(self.run.close)
        return self.run.start()

    def response(self, text, delay=0):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created(text),
                    ev_assistant_message("msg-" + text, text),
                    ev_completed(text),
                ]
            ),
            delay_between_events_s=delay,
        )


class SdkWorkflowsTest(SdkFixture):
    def test_group_is_concurrent_fresh_and_continues_same_worker(self):
        for i in range(4):
            self.response(f"review-{i}", delay=0.3)
        run = self.start(tokens=250000)
        results = run.bridge.group([{"prompt": f"private-task-{i}"} for i in range(4)])
        self.assertEqual(
            {r["text"] for r in results}, {f"review-{i}" for i in range(4)}
        )
        self.assertEqual({r["status"] for r in results}, {"completed"})
        requests = self.mock.requests()
        self.assertEqual(len(requests), 4)
        for request in requests:
            body = request.body_json()
            self.assertEqual(body["model"], "mock-model")
            self.assertEqual(body["max_output_tokens"], 16000)
            self.assertEqual(
                sum(f"private-task-{i}" in str(body["input"]) for i in range(4)), 1
            )
        deadline = time.monotonic() + 3
        while run.ledger.snapshot()["in_flight"] and time.monotonic() < deadline:
            time.sleep(0.02)
        events = [
            json.loads(line)
            for line in (self.root / "run/usage.jsonl").read_text().splitlines()
        ]
        dispatched = [e["unix_ms"] for e in events if e["type"] == "usage_dispatched"]
        finished = [e["unix_ms"] for e in events if e["type"] == "usage_finished"]
        self.assertLess(max(dispatched), min(finished))
        self.response("patched")
        continued = run.bridge.continue_worker(
            results[0]["worker_id"], "patch-same-worker"
        )
        self.assertEqual(continued["thread_id"], results[0]["thread_id"])
        captured = [
            json.loads(line)
            for line in (run.artifacts / "session/invocations.jsonl")
            .read_text()
            .splitlines()
        ]
        prompts = [
            event["prompt"] for event in captured if event["type"] == "turn_prompt"
        ]
        self.assertEqual(
            sorted(prompts),
            sorted([f"private-task-{i}" for i in range(4)] + ["patch-same-worker"]),
        )
        self.assertIn(
            "private-task-0", str(self.mock.requests()[-1].body_json()["input"])
        )
        receipt = run.close()
        self.assertEqual(receipt["usage"]["observed_tokens"], 10)
        self.assertEqual(receipt["usage"]["unknown_requests"], 0)
        self.assertIsNone(receipt["usage"]["observed_cached_input_tokens"])
        self.assertEqual(receipt["process"]["process_stop"], "confirmed")

    def test_reentrant_dynamic_callback_uses_actual_sdk_and_runtime(self):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("dispatch"),
                    ev_function_call(
                        "call-workers",
                        "run_workers",
                        json.dumps({"workers": [{"prompt": "child-only"}]}),
                    ),
                    ev_completed("dispatch"),
                ]
            )
        )
        self.response("child-result")
        self.response("parent-done")
        run = self.start()
        result = run.parent("parent-only")
        self.assertEqual(result["text"], "parent-done")
        requests = self.mock.requests()
        self.assertEqual(len(requests), 3)
        self.assertNotIn("parent-only", str(requests[1].body_json()["input"]))
        self.assertIn("child-result", str(requests[2].body_json()["input"]))
        self.assertEqual(run.close()["usage"]["observed_tokens"], 6)

    def test_fanout_budget_stops_admission_and_all_workers(self):
        for i in range(4):
            self.response(f"slow-{i}", delay=0.8)
        run = self.start(requests=2)
        try:
            run.bridge.group([{"prompt": str(i)} for i in range(4)])
        except Exception:
            pass
        receipt = run.close()
        self.assertLessEqual(len(self.mock.requests()), 2)
        self.assertTrue(receipt["usage"]["admission_stopped"])
        self.assertEqual(receipt["usage"]["in_flight"], 0)
        self.assertEqual(receipt["process"]["process_stop"], "confirmed")

    def test_user_question_gets_real_host_answer(self):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("question"),
                    ev_function_call(
                        "ask-1",
                        "request_user_input",
                        json.dumps(
                            {
                                "questions": [
                                    {
                                        "id": "scope",
                                        "header": "Scope",
                                        "question": "Which scope?",
                                        "options": [
                                            {
                                                "label": "Small",
                                                "description": "One change",
                                            },
                                            {
                                                "label": "Large",
                                                "description": "Several changes",
                                            },
                                        ],
                                    }
                                ]
                            }
                        ),
                    ),
                    ev_completed("question"),
                ]
            )
        )
        self.response("answered")
        run = self.start()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run.parent, "Ask about scope")
            params, answer = run.interactions.questions.get(timeout=10)
            self.assertEqual(params["questions"][0]["id"], "scope")
            answer.set_result({"scope": ["Small"]})
            self.assertEqual(future.result(timeout=10)["text"], "answered")
        self.assertIn("Small", str(self.mock.requests()[-1].body_json()["input"]))

    def test_delayed_callback_does_not_block_close(self):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("delayed"),
                    ev_function_call(
                        "late",
                        "run_workers",
                        json.dumps({"workers": [{"prompt": "unused"}]}),
                    ),
                    ev_completed("delayed"),
                ]
            )
        )
        run = self.start()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def delayed(method, params):
            entered.set()
            release.wait(20)
            return {
                "contentItems": [{"type": "inputText", "text": "late"}],
                "success": True,
            }

        run.session.callback = delayed
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run.parent, "Call the worker")
            self.assertTrue(entered.wait(10))
            started = time.monotonic()
            receipt = run.close()
            self.assertLess(time.monotonic() - started, 8)
            self.assertFalse(receipt["process"]["callbacks_stopped"])
            self.assertEqual(receipt["process"]["stop_status"], "unconfirmed")
            release.set()
            try:
                future.result(timeout=5)
            except Exception:
                pass
        self.assertEqual(len(self.mock.requests()), 1)

    def test_delayed_callback_cannot_write_into_restarted_sdk_process(self):
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("old"),
                    ev_function_call(
                        "old-call",
                        "run_workers",
                        json.dumps({"workers": [{"prompt": "unused"}]}),
                    ),
                    ev_completed("old"),
                ]
            )
        )
        run = self.start()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def delayed(method, params):
            entered.set()
            release.wait(20)
            return {
                "contentItems": [{"type": "inputText", "text": "old-reply"}],
                "success": True,
            }

        run.session.callback = delayed
        with ThreadPoolExecutor(max_workers=1) as pool:
            turn = pool.submit(run.parent, "Call a tool")
            self.assertTrue(entered.wait(10))
            run.close()
            process = SessionProcess(
                self.pin, self.root / "restarted-home", self.root / "restarted.json"
            )
            client = run.session.client
            client.config.launch_args_override = process.launch_args()
            client.start()
            self.addCleanup(client.close)
            client.initialize()
            process.launched()
            stream = client._proc.stdin
            recorder = Mock(wraps=stream)
            client._proc.stdin = recorder
            release.set()
            for thread in run.session.executor.threads:
                thread.join(timeout=2)
            recorder.write.assert_not_called()
            # The new process is still healthy after the stale callback returns.
            self.assertIn("data", run.session.request("thread/list", {}))
            client.close()
            self.assertTrue(process.stopped())
            try:
                turn.result(timeout=5)
            except Exception:
                pass

    def test_interrupt_stops_background_terminal_and_detached_child(self):
        heartbeat = self.workspace / "heartbeat"
        (self.workspace / "heartbeat.py").write_text(
            "import time\nfrom pathlib import Path\nwhile True:\n    Path('heartbeat').write_text(str(time.time()))\n    time.sleep(0.05)\n"
        )
        (self.workspace / "parent.py").write_text(
            "import subprocess,time\nsubprocess.Popen(['python3','heartbeat.py'],start_new_session=True)\ntime.sleep(120)\n"
        )
        command = "python3 parent.py"
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("shell"),
                    ev_function_call(
                        "shell-1",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": command,
                                "yield_time_ms": 1000,
                                "max_output_tokens": 1000,
                            }
                        ),
                    ),
                    ev_completed("shell"),
                ]
            )
        )
        self.response("waiting", delay=10)
        run = self.start(seconds=60)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                run.bridge.group,
                [{"prompt": "Start a background command", "writable": True}],
            )
            deadline = time.monotonic() + 30
            while not heartbeat.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(
                heartbeat.exists(),
                str([r.body_json().get("input") for r in self.mock.requests()])[-5000:],
            )
            worker_id = next(iter(run.bridge.children))
            terminals = run.session.request(
                "thread/backgroundTerminals/list",
                {"threadId": run.session.threads[worker_id]},
            )
            while not terminals["data"] and time.monotonic() < deadline:
                time.sleep(0.05)
                terminals = run.session.request(
                    "thread/backgroundTerminals/list",
                    {"threadId": run.session.threads[worker_id]},
                )
            self.assertTrue(terminals["data"])
            run.session.interrupt()
            self.assertEqual(future.result(timeout=10)[0]["status"], "interrupted")
            receipt = run.close()
        self.assertEqual(receipt["process"]["stop_status"], "confirmed")
        last = heartbeat.read_text()
        time.sleep(0.3)
        self.assertEqual(heartbeat.read_text(), last)
        events = [
            json.loads(line)
            for line in (self.root / "run/session/session.jsonl")
            .read_text()
            .splitlines()
        ]
        self.assertTrue(any(e["type"] == "interrupt_acknowledged" for e in events))
        self.assertTrue(
            any(
                e["type"] == "turn_completed" and e["status"] == "interrupted"
                for e in events
            )
        )


if __name__ == "__main__":
    unittest.main()
