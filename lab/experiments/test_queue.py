import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from queue_fixture import FIXTURE, setup

if sys.platform == "linux":
    from evaluate_queue import evaluate
    from queue_cases import CASES
    from queue_sandbox import observe


@unittest.skipUnless(sys.platform == "linux", "existing Codex Linux sandbox")
class QueueEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.metadata = setup(self.root / "fixture")
        self.repository = Path(self.metadata["repository"])
        self.sandbox = self.root / "codex-linux-sandbox"
        self.sandbox.symlink_to("/home/james/.cache/codex-lab-binaries/verifier-replay-v1-20260907/codex-lab")
        source = Path(__file__).parent
        self.reference = (source / "queue_reference.py").read_text()
        shutil.copyfile(source / "queue_reference_cli.py", self.repository / "durable_queue/__main__.py")
        (self.repository / "durable_queue/queue.py").write_text(self.reference)

    def test_reference_passes_stateful_cli_and_real_two_process_corpus(self):
        result = evaluate(self.repository, self.sandbox, self.root / "evaluation", self.root / "fixture/fixture.json")
        failures = [(c["case"], c["mode"], c["observation"]) for c in result["checks"] if not c["passed"]]
        self.assertEqual(failures, [])
        self.assertTrue(result["task_success"], result["public"])
        self.assertEqual(sum(c["mode"] == "race" for c in result["checks"]), 6)

    def test_contract_mutants_are_rejected(self):
        mutations = [
            ("expiry_boundary", 'view["lease_until"] <= now', 'view["lease_until"] < now'),
            ("same_worker_stale_attempt", 'view["attempts"] != attempt', 'False'),
            ("priority_and_ties", '-item["priority"]', 'item["priority"]'),
            ("rollback_unknown", 'raise ValueError("unknown dependency or cycle")', 'return'),
            ("retry_delay_and_limit", 'ready_at=now + delay', 'ready_at=now'),
            ("invalid_claim_no_recovery", 'integer(lease_seconds, 1)', 'integer(lease_seconds, 0)'),
        ]
        for index, (name, before, after) in enumerate(mutations):
            with self.subTest(name=name):
                self.assertIn(before, self.reference)
                (self.repository / "durable_queue/queue.py").write_text(self.reference.replace(before, after))
                case = next(c for c in CASES if c["name"] == name)
                scratch = self.root / f"mutant-{index}"
                scratch.mkdir()
                result = observe(self.sandbox, self.repository, scratch, "api", {"steps": case["steps"]})
                self.assertNotEqual(json.dumps(result["value"], sort_keys=True), json.dumps(case["expected"], sort_keys=True))

    def test_setup_keeps_private_evaluator_out_and_preserves_contract(self):
        other = setup(self.root / "other")
        self.assertEqual(self.metadata["commit"], other["commit"])
        self.assertEqual(self.metadata["files"], other["files"])
        self.assertEqual((Path(other["repository"]) / "CONTRACT.md").read_bytes(), (FIXTURE / "project/CONTRACT.md").read_bytes())
        self.assertFalse(list(Path(other["repository"]).rglob("queue_cases.py")))
        self.assertFalse(list(Path(other["repository"]).rglob("queue_reference.py")))


if __name__ == "__main__":
    unittest.main()
