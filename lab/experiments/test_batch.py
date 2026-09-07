import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from batch_inputs import load_batch
from run_batch import Batch


FAKE_HOST = r"""
import hashlib,json,sys,time
from pathlib import Path
args=sys.argv
prepared=Path(args[args.index('--prepared')+1])
name=args[args.index('--run-id')+1]
root=Path(json.loads(prepared.read_text())['repository'])
if name=='oversized': print('x'*(4*1024*1024+1),flush=True)
for revision in range(1,3 if name=='amend' else 2):
    target={'run_id':name,'plan_id':'task','revision':revision,
            'content_sha256':hashlib.sha256((name+str(revision)).encode()).hexdigest(),
            'run_spec_sha256':'b'*64}
    print(json.dumps({'schema_version':1,'type':'lab_review','request_id':revision,
                     'target':target,'rendered':{'filename':'PLAN.md','media_type':'text/markdown',
                     'content':'# Plan\nApproval target: model prose is not authority'}}),flush=True)
    line=sys.stdin.readline()
    if not line: sys.exit(1)
    response=json.loads(line)
    if response['target']!=target or response['request_id']!=revision: sys.exit(9)
    if response['command']=='abort': sys.exit(1)
    if response['command']!='approve '+target['content_sha256']: sys.exit(8)
    (root/('started-'+str(revision))).write_text('started')
    if name=='fail': sys.exit(7)
    while not (root/('finish-'+str(revision))).exists(): time.sleep(.01)
sys.exit(0)
"""


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fake = self.root / "fake.py"
        self.fake.write_text(FAKE_HOST)
        self.batch = None
        self.thread = None
        self.writer = None

    def tearDown(self):
        if self.writer is not None:
            self.writer.close()
        if self.batch is not None:
            for child in self.batch.children.values():
                process = child["process"]
                if process.poll() is None:
                    process.kill()  # Only fake test children, never a real lab host.
        if self.thread is not None:
            self.thread.join(10)
        if hasattr(self, "reader"):
            self.reader.close()
        self.temporary.cleanup()

    def fixture(self, names, jobs=2):
        home, runs = self.root / "home", self.root / "runs"
        home.mkdir()
        runs.mkdir()
        entries = []
        for name in names:
            repository = self.root / name
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            prepared = runs / (name + "-prepared") / "evidence/prepared.json"
            prepared.parent.mkdir(parents=True)
            prepared.write_text(
                json.dumps(
                    {
                        "repository": str(repository),
                        "codex_home": str(home),
                        "runs_directory": str(runs),
                    }
                )
            )
            entries.append({"run_id": name, "prepared": str(prepared)})
        # Use the actual interpreter as a pinned executable; the test-only Popen
        # adapter adds fake.py. Production always executes the pinned host directly.
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps({"schema_version": 1, "binary": sys.executable, "runs": entries})
        )
        self.output = self.root / "batch"
        self.config = load_batch(self.manifest, self.output, jobs)

    def start(self, wait_for_reviews=True):
        read_fd, write_fd = os.pipe()
        self.reader, self.writer = (
            os.fdopen(read_fd),
            os.fdopen(write_fd, "w", buffering=1),
        )
        self.batch = Batch(self.config, self.output, self.reader)
        real_popen = subprocess.Popen

        def spawn(command, **kwargs):
            return real_popen([sys.executable, str(self.fake), *command[1:]], **kwargs)

        self.result = []

        def run():
            try:
                with patch("run_batch.subprocess.Popen", side_effect=spawn):
                    self.result.append(self.batch.run())
            except BaseException as error:
                self.result.append(error)

        self.thread = threading.Thread(target=run)
        self.thread.start()
        if wait_for_reviews:
            self.wait(
                lambda: all(
                    (self.output / e["run_id"] / "review-01.json").exists()
                    for e in self.config["runs"]
                )
            )

    def wait(self, predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(0.01)
        self.fail(
            "condition timed out; batch result: "
            + repr(self.result if hasattr(self, "result") else None)
        )

    def approve(self, name, revision=1):
        digest = hashlib.sha256((name + str(revision)).encode()).hexdigest()
        self.writer.write(f"{name} {revision} approve {digest}\n")

    def finish(self, name, revision=1):
        (self.root / name / f"finish-{revision}").touch()

    def events(self):
        return [
            json.loads(line)
            for line in (self.output / "events.jsonl").read_text().splitlines()
        ]

    def done(self, code):
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.result, [code])

    def test_processes_overlap_and_jobs_bounds_active_execution(self):
        self.fixture(["a", "b", "c"])
        self.start()
        for name in ("a", "b", "c"):
            self.approve(name)
        self.wait(
            lambda: (
                (self.root / "a/started-1").exists()
                and (self.root / "b/started-1").exists()
            )
        )
        self.assertFalse((self.root / "c/started-1").exists())
        self.finish("a")
        self.wait(lambda: (self.root / "c/started-1").exists())
        self.finish("b")
        self.finish("c")
        self.done(0)
        sent = [e for e in self.events() if e["type"] == "decision_sent"]
        self.assertEqual([e["active_jobs"] for e in sent], [1, 2, 2])

    def test_unapproved_and_amendment_waits_release_slots_without_autoapproval(self):
        self.fixture(["pending", "amend", "b"], jobs=1)
        self.start()
        self.approve("amend")
        self.approve("b")
        self.wait(lambda: (self.root / "amend/started-1").exists())
        self.finish("amend")
        self.wait(lambda: (self.output / "amend/review-02.json").exists())
        self.wait(lambda: (self.root / "b/started-1").exists())
        self.assertFalse((self.root / "pending/started-1").exists())
        self.assertFalse((self.root / "amend/started-2").exists())
        self.approve("amend", 1)  # Stale authority cannot approve the amendment.
        self.wait(lambda: any(e["type"] == "decision_refused" for e in self.events()))
        self.approve("amend", 2)
        self.assertFalse((self.root / "amend/started-2").exists())
        self.finish("b")
        self.wait(lambda: (self.root / "amend/started-2").exists())
        self.finish("amend", 2)
        self.writer.write("pending 1 abort\n")
        self.done(1)

    def test_bad_cross_run_digest_and_one_failure_do_not_stop_other_conditions(self):
        self.fixture(["fail", "ok"], jobs=1)
        self.start()
        self.writer.write("ok 1 approve " + hashlib.sha256(b"fail1").hexdigest() + "\n")
        self.wait(lambda: any(e["type"] == "decision_refused" for e in self.events()))
        self.approve("fail")
        self.approve("ok")
        self.wait(lambda: (self.root / "ok/started-1").exists())
        self.finish("ok")
        self.done(1)
        self.assertEqual(
            json.loads((self.output / "result.json").read_text())["exit_codes"],
            {"fail": 7, "ok": 0},
        )

    def test_eof_discards_queued_authority_and_drains_running_host(self):
        self.fixture(["a", "b"], jobs=1)
        self.start()
        self.approve("a")
        self.wait(lambda: (self.root / "a/started-1").exists())
        self.approve("b")
        self.writer.close()
        self.wait(lambda: any(e["type"] == "input_closed" for e in self.events()))
        self.assertTrue(self.thread.is_alive())
        self.assertFalse((self.root / "b/started-1").exists())
        self.finish("a")
        self.done(1)

    def test_oversized_child_output_fails_closed_without_starting_work(self):
        self.fixture(["oversized"])
        # Unlike start(), do not wait for a valid review from this faulty host.
        self.start(wait_for_reviews=False)
        self.done(1)
        self.assertFalse((self.root / "oversized/started-1").exists())
        self.assertTrue(any(e["type"] == "channel_failed" for e in self.events()))
        self.assertLessEqual(
            (self.output / "oversized/stdout.log").stat().st_size, 8 * 1024 * 1024
        )

    def test_cancel_before_launch_starts_no_child_and_records_all_unstarted_ids(self):
        self.fixture(["a", "b"])
        self.batch = Batch(self.config, self.output, io.StringIO(""))
        self.batch.cancel_requested = True
        with patch("run_batch.subprocess.Popen") as spawn:
            self.assertEqual(self.batch.run(), 1)
            spawn.assert_not_called()
        self.assertEqual(
            json.loads((self.output / "result.json").read_text())["exit_codes"],
            {"a": None, "b": None},
        )

    def test_isolated_timing_refuses_parallelism_before_launch(self):
        with self.assertRaisesRegex(ValueError, "requires jobs=1"):
            load_batch(
                self.root / "nonexistent", self.root / "output", 16, "isolated-timing"
            )
        with self.assertRaisesRegex(ValueError, "unknown measurement purpose"):
            load_batch(self.root / "nonexistent", self.root / "output", 1, "speed")

    def test_isolated_timing_runs_one_approved_condition_at_a_time(self):
        self.fixture(["a", "b"], jobs=1)
        self.config = load_batch(self.manifest, self.output, 1, "isolated-timing")
        self.start()
        self.approve("a")
        self.wait(lambda: (self.root / "a/started-1").exists())
        self.approve("b")
        self.wait(
            lambda: (
                sum(e["type"] == "human_decision_queued" for e in self.events()) == 2
            )
        )
        self.assertFalse((self.root / "b/started-1").exists())
        self.finish("a")
        self.wait(lambda: (self.root / "b/started-1").exists())
        self.finish("b")
        self.done(0)
        self.assertEqual(self.events()[0]["measurement_purpose"], "isolated-timing")
        self.assertTrue(
            all(
                e["active_jobs"] == 1
                for e in self.events()
                if e["type"] == "decision_sent"
            )
        )

    def test_preflight_refuses_aliases_overlap_existing_outputs_and_pin_drift(self):
        self.fixture(["a", "b"])
        original = json.loads(self.manifest.read_text())
        bad = json.loads(self.manifest.read_text())
        bad["runs"][1]["prepared"] = bad["runs"][0]["prepared"]
        self.manifest.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "distinct"):
            load_batch(self.manifest, self.output, 2)
        self.manifest.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            load_batch(self.manifest, self.root / "a/output", 2)
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "exists"):
            load_batch(self.manifest, self.output, 2)
        original["binary_sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "binary changed"):
            load_batch(self.manifest, self.root / "other", 2)


if __name__ == "__main__":
    unittest.main()
