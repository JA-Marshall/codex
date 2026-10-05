"""Actual SDK ↔ authenticated HTTP broker ↔ durable reviewer response mechanics."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
import shlex
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from provider_rate_limit import SharedLimiter
from workflows.human_review import HumanReview
from workflows.metered_run import MeteredRun
from workflows.review_client import ReviewClient
from workflows.review_server import ReviewServer
from workflows.review_store import ReviewStore
from workflows.trial_clock import TrialClock
from workflows.usage import Budget
from workflows.filesystem import SessionSandbox
from openai_codex.errors import TransportClosedError


class HumanReviewTest(SdkFixture):
    def setUp(self):
        super().setUp()
        self.store = ReviewStore(self.root / "broker/review.sqlite")
        self.server = ReviewServer(self.store)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.browser = build_opener(HTTPCookieProcessor())
        self.csrf = self.http("/api/session", {"token": self.server.reviewer_token})["csrf"]

    def http(self, path, payload=None, *, headers=None):
        fields = {"Origin": self.server.origin, "Content-Type": "application/json", "X-Review-CSRF": getattr(self, "csrf", "")}
        fields.update(headers or {})
        request = Request(self.server.origin + path, data=json.dumps(payload).encode() if payload is not None else None, headers=fields)
        with self.browser.open(request, timeout=3) as response:
            return json.load(response)

    def wait_ready(self, count):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            ready = [r for r in self.http("/api/reviews") if r["state"] == "pending"]
            if len(ready) == count:
                return ready
            time.sleep(0.05)
        self.fail("actual runtime reviews did not become ready")

    def test_two_actual_questions_route_exact_responses_without_identity_leaks(self):
        runs, futures, reviews = [], [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            try:
                for i in range(2):
                    self.mock.enqueue_sse(sse([ev_response_created(f"ask-{i}"), ev_function_call(f"ask-{i}", "request_user_input", json.dumps({"questions": [{"id": "retention", "header": "Retention", "question": "How many days should records be retained?", "options": [{"label": "30 days", "description": "Recent records"}, {"label": "90 days", "description": "Older records"}]}]})), ev_completed(f"ask-{i}")]))
                    workspace = self.root / f"workspace-{i}"
                    workspace.mkdir()
                    run = MeteredRun(run_id=f"private-run-{i}", pin=self.pin, workspace=workspace,
                                     artifacts=self.root / f"runtime-{i}", model="mock-model", budget=Budget(8,1000000,60),
                                     shared_upstream=self.mock.url+"/v1", upstream_key="mock", limiter=SharedLimiter(startup_delay=0,window=0.1),
                                     clock=TrialClock(60), allow_workers=False)
                    runs.append(run)
                    run.start()
                    run.human_review = HumanReview(run, ReviewClient(self.server.origin,self.server.runner_token),
                                                  trial=f"secret-trial-{i}", block="block", scenario=f"scenario-{i}",
                                                  title="Retention filter",original_request="Filter records using the owner's retention policy.")
                    futures.append(pool.submit(run.parent,"Ask for the missing retention policy."))
                    reviews = self.wait_ready(i+1)
                self.assertEqual(len(self.mock.requests()),2)
                self.assertNotIn("private",json.dumps(reviews))
                self.assertNotIn("secret",json.dumps(reviews))
                for i in (1,0):
                    review=reviews[i]
                    detail=self.http('/api/reviews/'+review['id'])
                    payload=dict(key=f'response-key-{i}',revision=detail['revision'],presented_hash=detail['presented_hash'],action='answer',answers={'retention':[f'Exactly {37+i} days.']})
                    self.response(f"continued-{i}")
                    receipt=self.http('/api/reviews/'+review['id']+'/response',payload)
                    self.assertEqual(self.http('/api/reviews/'+review['id']+'/response',payload),receipt)
                    self.assertEqual(futures[i].result(timeout=10)['text'],f'continued-{i}')
                    self.assertIn(f'Exactly {37+i} days.',str(self.mock.requests()[-1].body_json()['input']))
                    self.assertNotIn(f'Exactly {38-i} days.',str(self.mock.requests()[-1].body_json()['input']))
                    self.assertTrue(runs[i].human_review.pending_ack.wait(3))
                    self.assertIsNotNone(self.http('/api/reviews/'+review['id'])['continued'])
            finally:
                for run in runs:
                    if run.human_review and run.human_review.pause.boundary:
                        run.human_review.pause.interrupt()
                    run.close()

    def test_authentication_and_origin_surfaces_are_separate(self):
        with self.assertRaises(HTTPError) as error:
            self.http('/runner/register',{},headers={'Authorization':'Bearer '+self.server.reviewer_token})
        self.assertEqual(error.exception.code,403)

    def test_broker_restart_preserves_actual_pending_callback(self):
        self.mock.enqueue_sse(sse([ev_response_created('restart-question'),ev_function_call('restart-question','request_user_input',json.dumps({'questions':[{'id':'policy','header':'Policy','question':'Which retention policy?','options':[{'label':'30 days','description':'Recent records'},{'label':'90 days','description':'Older records'}]}]})),ev_completed('restart-question')]))
        run=self.start(clock=TrialClock(30))
        run.human_review=HumanReview(run,ReviewClient(self.server.origin,self.server.runner_token),trial='restart-trial',block='restart-block',scenario='restart-scenario',title='Retention filter',original_request='Ask for the retention policy.')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(run.parent,'Ask the owner for policy')
            try:
                review=self.wait_ready(1)[0]
                before=run.ledger.snapshot()
                port,reviewer,runner=self.server.server_port,self.server.reviewer_token,self.server.runner_token
                self.server.shutdown()
                self.server.server_close()
                time.sleep(.8)
                self.assertFalse(future.done())
                self.assertEqual(run.ledger.snapshot(),before)
                self.store=ReviewStore(self.root/'broker/review.sqlite')
                self.server=ReviewServer(self.store,port=port,reviewer_token=reviewer,runner_token=runner)
                threading.Thread(target=self.server.serve_forever,daemon=True).start()
                self.addCleanup(self.server.server_close)
                self.addCleanup(self.server.shutdown)
                self.assertEqual(self.http('/api/session')['csrf'],self.csrf)
                detail=self.http('/api/reviews/'+review['id'])
                self.assertEqual(detail['state'],'pending')
                self.response('continued-after-service-restart')
                self.http('/api/reviews/'+review['id']+'/response',dict(key='restart-answer',revision=detail['revision'],presented_hash=detail['presented_hash'],action='answer',answers={'policy':['Exactly 41 days.']}))
                result=future.result(timeout=10)
                self.assertEqual(result['text'],'continued-after-service-restart')
                self.assertGreater(run.clock.snapshot()['elapsed']['outage'],.2)
                self.assertEqual(len(self.mock.requests()),2)
                self.assertIn('Exactly 41 days.',str(self.mock.requests()[-1].body_json()['input']))
                self.assertTrue(run.human_review.pending_ack.wait(3))
            finally:
                if run.human_review.pause.boundary: run.human_review.pause.interrupt()

    def test_actual_candidate_sandbox_cannot_read_broker_or_connect(self):
        script = (
            "import json,urllib.request\nfrom pathlib import Path\nresult={}\n"
            "try:\n Path("+repr(str(self.store.path))+").read_bytes()\n result['broker_files_readable']=True\n"
            "except OSError:\n result['broker_files_readable']=False\n"
            "try:\n urllib.request.urlopen("+repr(self.server.origin+'/api/reviews')+",timeout=1)\n result['broker_network_reachable']=True\n"
            "except urllib.error.HTTPError:\n result['broker_network_reachable']=True\n"
            "except OSError:\n result['broker_network_reachable']=False\n"
            "print(json.dumps(result,sort_keys=True))\n"
        )
        self.mock.enqueue_sse(sse([ev_response_created('sandbox-probe'),ev_function_call('sandbox-probe','exec_command',json.dumps({'cmd':'python3 -c '+shlex.quote(script),'max_output_tokens':1000})),ev_completed('sandbox-probe')]))
        self.response('sandbox-probe-finished')
        run=self.start(sandbox=SessionSandbox(self.workspace),clock=TrialClock(30))
        self.assertEqual(run.parent('Run the bounded isolation probe')['text'],'sandbox-probe-finished')
        outputs=[item.get('output','') for item in self.mock.requests()[-1].body_json()['input'] if item.get('type')=='function_call_output']
        self.assertTrue(outputs)
        output='\n'.join(str(value) for value in outputs)
        self.assertIn('"broker_files_readable": false',output)
        self.assertIn('"broker_network_reachable": false',output)

    def test_actual_paused_runtime_loss_is_interrupted_without_retry(self):
        self.mock.enqueue_sse(sse([ev_response_created('lost-question'),ev_function_call('lost-question','request_user_input',json.dumps({'questions':[{'id':'policy','header':'Policy','question':'Which policy?','options':[{'label':'30 days','description':'Recent records'},{'label':'90 days','description':'Older records'}]}]})),ev_completed('lost-question')]))
        run=self.start(clock=TrialClock(30))
        run.human_review=HumanReview(run,ReviewClient(self.server.origin,self.server.runner_token),trial='lost-trial',block='lost-block',scenario='lost-scenario',title='Retention filter',original_request='Ask the owner for the missing policy.')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(run.parent,'Ask for policy')
            review=self.wait_ready(1)[0]
            process=run.session.client._proc
            run.human_review.pause.processes.terminate()
            try:
                result=future.result(timeout=10)
                self.assertNotEqual(result['status'],'completed')
            except (RuntimeError,OSError,TransportClosedError):
                pass
            deadline=time.monotonic()+3
            while self.http('/api/reviews/'+review['id'])['state']!='interrupted' and time.monotonic()<deadline:
                time.sleep(.05)
            self.assertEqual(self.http('/api/reviews/'+review['id'])['state'],'interrupted')
            self.assertEqual(len(self.mock.requests()),1)
        self.assertEqual(run.close()['process']['process_stop'],'confirmed')
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)
        with self.assertRaises(HTTPError) as error:
            self.http('/api/reviews/invalid/response',{},headers={'Origin':'http://attacker.invalid'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            self.http('/api/reviews/invalid/response',{},headers={'X-Review-CSRF':'wrong'})
        self.assertEqual(error.exception.code,403)
