"""Durable decisions, cross-trial isolation and exact-once consume."""

from pathlib import Path
import tempfile
import unittest
import os
from unittest.mock import patch

from workflows.review_store import ReviewStore, ReviewConflict
from workflows.review_projection import project_question
from workflows.review_ownership import host_identity
from workflows.process_pause import process_stat
from workflows.review_timing import ReviewTiming


class ReviewStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "review.sqlite"
        self.store = ReviewStore(self.path)
        self.identity = host_identity({"pid": os.getpid(), "start_ticks": process_stat(os.getpid())[2], "namespace": os.readlink('/proc/self/ns/pid')})

    def ready(self, trial="one", scenario="scenario-one"):
        self.store.register(trial=trial, block="block", scenario=scenario, generation="generation", identity=self.identity, title="Retention filter")
        raw = {"threadId": "secret-thread", "questions": [{"id": "retention", "header": "Retention", "question": "Which policy?", "options": []}]}
        request = self.store.publish(trial=trial, generation="generation", revision=1, kind="clarification", raw=raw, presented=project_question(raw, request="Filter records"))
        identity = dict(request=request, trial=trial, generation="generation", revision=1)
        self.store.transition(**identity, state="pausing")
        self.store.transition(**identity, state="pending", evidence={"quiescent": True})
        return identity

    def answer(self, identity, **changes):
        detail = self.store.detail(identity["request"])
        args = dict(key="unique-key-one", revision=1, presented_hash=detail["presented_hash"], action="answer", answers={"retention": ["37 days"]})
        args.update(changes)
        return self.store.submit(identity["request"], **args)

    def test_restart_double_submission_and_consumption_are_durable(self):
        identity = self.ready()
        receipt = self.answer(identity)
        self.store = ReviewStore(self.path)
        self.assertEqual(self.answer(identity), receipt)
        self.assertEqual(self.store.detail(identity["request"])["state"], "answered")
        self.assertIsNone(self.store.detail(identity["request"])["continued"])
        with self.assertRaises(ReviewConflict):
            self.answer(identity, answers={"retention": ["90 days"]})
        answer = self.store.consume(**identity)
        self.assertEqual(answer["answers"], {"retention": ["37 days"]})
        with self.assertRaises(ReviewConflict):
            self.store.consume(**identity)
        self.store.continued(**identity, evidence={"next_provider_request": "observed-3"})
        self.assertIsNotNone(self.store.detail(identity["request"])["continued"])

    def test_wrong_generation_revision_and_cross_trial_never_consume(self):
        one, two = self.ready(), self.ready("two", "scenario-two")
        self.answer(one)
        for changes in ({"generation": "wrong"}, {"revision": 2}, {"trial": two["trial"]}):
            with self.assertRaises(ReviewConflict):
                self.store.consume(**(one | changes))
        with self.assertRaises(ReviewConflict):
            self.answer(two, revision=2, key="second-response")
        self.assertEqual(self.store.consume(**one)["answers"], {"retention": ["37 days"]})
        self.assertEqual(self.store.detail(two["request"])["state"], "pending")

    def test_two_slots_include_pauses_and_same_scenario_is_sequential(self):
        self.ready()
        with self.assertRaises(ReviewConflict):
            self.ready("same-scenario", "scenario-one")
        self.ready("two", "scenario-two")
        with self.assertRaises(ReviewConflict):
            self.ready("three", "scenario-three")

    def test_consumed_then_runner_crash_is_interrupted_without_replay(self):
        identity = self.ready()
        self.answer(identity)
        self.store.consume(**identity)
        self.store.interrupt("one", "generation", "runner lost before continuation")
        self.store = ReviewStore(self.path)
        with self.assertRaises(ReviewConflict):
            self.store.consume(**identity)
        detail = self.store.detail(identity["request"])
        self.assertEqual(detail["state"], "interrupted")
        self.assertIsNone(detail["continued"])

    def test_projection_has_no_raw_identity_or_grader(self):
        identity = self.ready()
        detail = self.store.detail(identity["request"])
        self.assertNotIn("secret", str(detail))
        self.assertNotIn("generation", detail)
        self.assertNotIn("raw", detail)
        self.assertNotIn("workflow", str(self.store.list_reviews()))

    def test_lost_publish_response_recovers_same_immutable_request(self):
        identity = self.ready()
        with self.store.transaction() as db:
            import json
            row = db.execute("SELECT * FROM reviews WHERE id=?", (identity["request"],)).fetchone()
            args = dict(trial="one", generation="generation", revision=1, kind="clarification", raw=json.loads(row["raw"]), presented=json.loads(row["presented"]))
        self.store = ReviewStore(self.path)
        self.assertEqual(self.store.publish(**args), identity["request"])
        with self.assertRaises(ReviewConflict):
            self.store.publish(**(args | {"raw": {"changed": True}}))

    def test_nested_internal_fields_rejected_at_broker_boundary(self):
        self.store.register(trial="one", block="block", scenario="scenario", generation="generation", identity=self.identity, title="Retention")
        raw = {"questions": [{"id": "retention", "header": "Retention", "question": "Which policy?", "options": []}]}
        presented = project_question(raw, request="Filter records")
        presented["questions"][0]["internal_identity"] = {"workflow": "BMAD_CANARY"}
        with self.assertRaises(ValueError):
            self.store.publish(trial="one", generation="generation", revision=1, kind="clarification", raw=raw, presented=presented)

    def test_timer_one_tab_disconnect_and_manual_adjustment(self):
        request = self.ready()["request"]
        timing = ReviewTiming(self.store)
        with patch('workflows.review_timing.time.time', return_value=100):
            timing.update(request=request, tab="first-tab", action="start")
        with patch('workflows.review_timing.time.time', return_value=102):
            with self.assertRaises(ReviewConflict):
                timing.update(request=request, tab="second-tab", action="start")
            timing.update(request=request, tab="first-tab", action="heartbeat")
        with patch('workflows.review_timing.time.time', return_value=200):
            stopped = timing.update(request=request, tab="first-tab", action="status")
            self.assertEqual(stopped, {"seconds":2, "running":False, "this_tab":False})
            timing.update(request=request, tab="second-tab", action="start")
        with patch('workflows.review_timing.time.time', return_value=201):
            timing.update(request=request, tab="second-tab", action="pause")
            adjusted = timing.update(request=request, tab="second-tab", action="adjust", seconds=-1, reason="Correct an accidental timer start")
            self.assertEqual(adjusted["seconds"],2)

    def test_dead_runtime_generation_cannot_consume(self):
        identity=self.ready()
        self.answer(identity)
        with self.store.transaction() as db:
            import json
            broken=dict(self.identity,boot_id="previous-boot")
            db.execute("UPDATE trials SET identity=?", (json.dumps(broken),))
        with self.assertRaises(ReviewConflict):
            self.store.consume(**identity)
        self.store.reconcile_ownership()
        self.assertEqual(self.store.detail(identity["request"])["state"],"interrupted")

    def test_active_timer_adjustment_and_answer_commit_stop_are_atomic(self):
        identity=self.ready()
        timing=ReviewTiming(self.store)
        with patch('workflows.review_timing.time.time',return_value=100):
            timing.update(request=identity['request'],tab='first-tab',action='start')
        for second in (102,104,106,108,110):
            with patch('workflows.review_timing.time.time',return_value=second):
                timing.update(request=identity['request'],tab='first-tab',action='heartbeat')
        with patch('workflows.review_timing.time.time',return_value=110):
            adjusted=timing.update(request=identity['request'],tab='first-tab',action='adjust',seconds=-5,reason='Five seconds counted accidentally')
            self.assertEqual(adjusted['seconds'],5)
            self.assertTrue(adjusted['this_tab'])
            self.answer(identity)
            stopped=timing.update(request=identity['request'],tab='first-tab',action='status')
            self.assertEqual(stopped,{'seconds':5,'running':False,'this_tab':False})

    def test_expiry_commits_before_late_response_is_rejected(self):
        identity=self.ready()
        with self.store.transaction() as db:
            db.execute("UPDATE reviews SET ready=ready-86401 WHERE id=?",(identity['request'],))
        with self.assertRaises(ReviewConflict):
            self.answer(identity)
        self.assertEqual(self.store.status(**identity)['state'],'expired')
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM answers').fetchone()[0],0)

    def test_withdrawal_keeps_no_resume_terminal_status(self):
        identity=self.ready()
        self.store.withdraw(identity['request'],reason='No longer useful')
        self.assertEqual(self.store.status(**identity)['state'],'withdrawn')
        with self.assertRaises(ReviewConflict):
            self.store.consume(**identity)
