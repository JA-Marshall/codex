"""Actual SDK transport pause, detached writes and shared-clock conservation."""

from concurrent.futures import ThreadPoolExecutor
import json
import time
import unittest

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.human_pause import HumanPause
from workflows.trial_clock import TrialClock


class HumanPauseTest(SdkFixture):
    def call(self, name, args, tag):
        self.mock.enqueue_sse(sse([ev_response_created(tag),
            ev_function_call(tag, name, json.dumps(args)), ev_completed(tag)]))

    def test_callback_stops_detached_writer_and_resumes_same_turn(self):
        (self.workspace / "heartbeat.py").write_text(
            "import time\nfrom pathlib import Path\nwhile True:\n"
            "    Path('heartbeat').write_text(str(time.time()))\n    time.sleep(0.05)\n")
        (self.workspace / "parent.py").write_text(
            "import subprocess,time\nsubprocess.Popen(['python3','heartbeat.py'],"
            "start_new_session=True)\ntime.sleep(120)\n")
        self.call("exec_command", {"cmd": "python3 parent.py", "yield_time_ms": 1000}, "write")
        self.call("request_user_input", {"questions": [{"id": "retention", "header": "Retention",
            "question": "How long should records be retained?", "options": [
                {"label": "30 days", "description": "Retain recent records"},
                {"label": "90 days", "description": "Retain older records"}]}]}, "ask")
        self.response("continued-exact-answer")
        clock = TrialClock(30)
        run = self.start(clock=clock)
        pause = HumanPause(run)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run.parent, "Start the writer, then ask the retention question.")
            params, answer = run.interactions.questions.get(timeout=15)
            try:
                evidence = pause.pause(kind="tool_callback")
                self.assertTrue(evidence["quiescent"])
                self.assertGreater(evidence["processes"], 1)
                last = (self.workspace / "heartbeat").read_text()
                charged = run.ledger.snapshot()
                before = clock.snapshot()["agent_seconds"]
                time.sleep(1)
                pause.verify()
                self.assertEqual((self.workspace / "heartbeat").read_text(), last)
                self.assertEqual(run.ledger.snapshot(), charged)
                self.assertEqual(clock.snapshot()["agent_seconds"], before)
                self.assertEqual(run.ledger.deadline, run.session.deadline)
                self.assertEqual(len(self.mock.requests()), 2)
                with self.assertRaisesRegex(RuntimeError, "pausing"):
                    run.session.new_thread("sibling")
                pause.resume()
                answer.set_result({"retention": ["Exactly 37 days, retaining original order."]})
                result = future.result(timeout=10)
                self.assertEqual(result["turn_id"], params["turnId"])
                self.assertEqual(result["thread_id"], params["threadId"])
                self.assertEqual(result["text"], "continued-exact-answer")
                self.assertIn("Exactly 37 days, retaining original order.",
                              str(self.mock.requests()[-1].body_json()["input"]))
            finally:
                if pause.boundary:
                    pause.interrupt()
                if not answer.done():
                    answer.set_result({"retention": ["Cannot decide"]})
        receipt = run.close()
        self.assertEqual(receipt["process"]["stop_status"], "confirmed")

    def test_completed_turn_pause_preserves_thread(self):
        self.response("proposal")
        self.response("approved-step")
        run = self.start(clock=TrialClock(30))
        initial = run.parent("Make one proposal")
        pause = HumanPause(run)
        pause.pause(kind="completed_turn")
        try:
            time.sleep(0.2)
            pause.verify()
            self.assertEqual(len(self.mock.requests()), 1)
            pause.resume()
            revised = run.parent("Approve this exact step")
            self.assertEqual(initial["thread_id"], revised["thread_id"])
            self.assertNotEqual(initial["turn_id"], revised["turn_id"])
            self.assertEqual(revised["text"], "approved-step")
        finally:
            if pause.boundary:
                pause.interrupt()

    def test_existing_sibling_stream_drains_before_pause_is_ready(self):
        self.response("sibling-finished", delay=0.7)
        self.call("request_user_input", {"questions": [{"id":"policy","header":"Policy","question":"Which policy?","options":[{"label":"30 days","description":"Short history"},{"label":"90 days","description":"Long history"}]}]}, "parent-question")
        self.response("parent-continued")
        clock = TrialClock(30)
        run = self.start(clock=clock)
        run.session.new_thread("existing-sibling")
        pause = HumanPause(run)
        with ThreadPoolExecutor(max_workers=2) as pool:
            sibling = pool.submit(run.session.turn,"existing-sibling","Complete this existing task")
            deadline = time.monotonic()+5
            while not self.mock.requests() and time.monotonic()<deadline:
                time.sleep(.01)
            parent = pool.submit(run.parent,"Ask for policy")
            _, answer = run.interactions.questions.get(timeout=10)
            try:
                self.assertGreater(run.ledger.snapshot()["in_flight"],0)
                pause.pause(kind="tool_callback")
                self.assertEqual(run.ledger.snapshot()["in_flight"],0)
                self.assertGreater(clock.snapshot()["elapsed"]["pausing"],0.3)
                snapshot = run.ledger.snapshot()
                time.sleep(.2)
                pause.verify()
                self.assertEqual(run.ledger.snapshot(),snapshot)
                pause.resume()
                answer.set_result({"policy":["Owner policy"]})
                self.assertEqual(sibling.result(timeout=5)["text"],"sibling-finished")
                self.assertEqual(parent.result(timeout=5)["text"],"parent-continued")
            finally:
                if pause.boundary: pause.interrupt()
                if not answer.done(): answer.set_result({"policy":["Cannot decide"]})


class TrialClockTest(unittest.TestCase):
    def test_commit_ends_human_wait_and_preserves_outage_category(self):
        current=[1000.0]
        clock=TrialClock(60,monotonic=lambda:current[0],wall=lambda:current[0])
        clock.transition("agent")
        current[0]+=5
        clock.transition("pausing")
        current[0]+=2
        clock.transition("human_wait")
        current[0]+=10
        clock.transition("outage")
        current[0]+=10
        clock.transition("human_wait")
        current[0]+=5
        clock.response_committed(1015)
        snapshot=clock.snapshot()
        self.assertEqual(snapshot["elapsed"]["human_wait"],8)
        self.assertEqual(snapshot["elapsed"]["outage"],10)
        self.assertEqual(snapshot["elapsed"]["handoff"],7)
        self.assertEqual(snapshot["agent_seconds"],7)
        clock.transition("agent")
        self.assertEqual(clock.deadline-current[0],53)
        clock.transition("terminal")
        current[0]+=1000
        self.assertEqual(clock.snapshot(),snapshot | {"state":"terminal"})

    def test_repeated_outages_never_extend_ready_expiry(self):
        current = [1000.0]
        clock = TrialClock(60, monotonic=lambda: current[0], wall=lambda: current[0])
        clock.transition("agent")
        clock.transition("pausing")
        clock.transition("human_wait")
        ready = clock.ready_at
        for _ in range(3):
            current[0] += 10
            clock.transition("outage")
            current[0] += 10
            clock.transition("human_wait")
            self.assertEqual(clock.ready_at, ready)
        while current[0] < ready + 86400:
            current[0] += 10
            clock.deadline
        self.assertTrue(clock.snapshot()["review_deadline_reached"])
        self.assertIsNone(clock.snapshot()["interruption"])
        self.assertEqual(clock.snapshot()["agent_seconds"], 0)

    def test_on_time_commit_learned_after_deadline_does_not_expire(self):
        current=[1000.0]
        clock=TrialClock(60,monotonic=lambda:current[0],wall=lambda:current[0])
        clock.transition('agent')
        clock.transition('pausing')
        clock.transition('human_wait')
        ready=clock.ready_at
        for _ in range(8641):
            current[0]+=10
            clock.deadline
        self.assertTrue(clock.snapshot()['review_deadline_reached'])
        clock.response_committed(ready+86399)
        clock.transition('agent')
        self.assertEqual(clock.deadline-current[0],60)
        self.assertFalse(clock.snapshot()['review_deadline_reached'])
        self.assertEqual(clock.snapshot()['elapsed']['human_wait'],86399)
        self.assertEqual(clock.snapshot()['elapsed']['handoff'],11)

    def test_overnight_wait_keeps_agent_allowance_and_wall_time(self):
        current = [0.0]
        clock = TrialClock(60, monotonic=lambda: current[0], wall=lambda: current[0])
        clock.transition("agent")
        current[0] += 10
        clock.transition("pausing")
        current[0] += 5
        clock.transition("human_wait")
        for _ in range(3600):
            current[0] += 10
            self.assertEqual(clock.deadline, float("inf"))
        clock.transition("agent")
        self.assertEqual(clock.deadline - current[0], 45)
        self.assertEqual(clock.snapshot()["elapsed"]["human_wait"], 36000)
        self.assertEqual(clock.snapshot()["wall_seconds"], 36015)

    def test_clock_jump_and_missing_heartbeat_interrupt(self):
        mono, wall = [0.0], [0.0]
        clock = TrialClock(60, monotonic=lambda: mono[0], wall=lambda: wall[0])
        clock.transition("agent")
        mono[0], wall[0] = 1, 100
        self.assertEqual(clock.deadline, 1)
        self.assertIsNotNone(clock.snapshot()["interruption"])
        with self.assertRaises(RuntimeError):
            clock.transition("agent")
