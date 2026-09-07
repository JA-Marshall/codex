import json
from pathlib import Path
import tempfile
import threading
import tomllib
import unittest

from setup_fixture import sha256
from setup_matrix import conditions, schedule, validate_pins


class MatrixTests(unittest.TestCase):
    def test_catalog_resolves_only_the_selected_role_differences(self):
        root = Path(__file__).resolve().parents[1]
        catalog = tomllib.loads((root / "workflows/queue-matrix.toml").read_text())
        base = catalog["workflows"]["queue-base"]
        resolved = {}
        for entry in conditions():
            profile = catalog["workflows"][entry["workflow"]]
            self.assertEqual(profile["extends"], "queue-base")
            roles = base["roles"] | profile.get("roles", {})
            for role, selector in roles.items():
                registered = catalog["skills"][selector]
                self.assertEqual(sha256(root / registered["path"] / "SKILL.md"), registered["sha256"])
                self.assertLess((root / registered["path"] / "SKILL.md").stat().st_size, 8192)
            resolved[entry["id"]] = roles
        entries = conditions()
        for left in entries:
            for right in entries:
                different = {role for role in ("planner", "executor", "verifier") if left[role] != right[role]}
                actual = {role for role in different | set(resolved[left["id"]]) if resolved[left["id"]][role] != resolved[right["id"]][role]}
                self.assertEqual(actual, different)
                if left["parent"] == right["id"]:
                    self.assertEqual(left["block"], right["block"])
                    self.assertEqual(left["planner"], right["planner"])

    def test_eight_planners_overlap_and_failed_plan_is_never_replaced(self):
        barrier = threading.Barrier(8)
        calls, emitted = [], []
        lock = threading.Lock()
        def worker(entry, parent):
            with lock:
                calls.append(entry["id"])
            if parent is None:
                barrier.wait(timeout=5)
                if entry["id"] == "queue-r1-aaa":
                    raise RuntimeError("record this failed sample")
            else:
                self.assertEqual(entry["parent"], parent["id"])
            return {"id": entry["id"], "status": "awaiting_plan_approval"}
        results = schedule(conditions(), worker, emitted.append)
        self.assertEqual(len(results), 32)
        self.assertEqual(len(calls), 29)
        self.assertEqual(len(set(calls)), len(calls))
        self.assertEqual([r["id"] for r in results if r["status"] == "failed"], ["queue-r1-aaa"])
        self.assertEqual(sum(r["status"] == "blocked_by_failed_plan" for r in results), 3)
        self.assertEqual(len(emitted), 32)

    def test_ready_plan_clones_do_not_wait_for_slowest_planner(self):
        clone_started = threading.Event()
        def worker(entry, parent):
            if entry["id"] == "queue-r4-baa":
                self.assertTrue(clone_started.wait(5), "unexpected global planner barrier")
            if parent is not None:
                clone_started.set()
            return {"id": entry["id"], "status": "awaiting_plan_approval"}
        self.assertTrue(all(r["status"] == "awaiting_plan_approval" for r in schedule(conditions(), worker, lambda result: None)))

    def test_changed_frozen_input_refuses_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps({"context": 100}))
            manifest = {"pins": {str(path): sha256(path)}}
            validate_pins(manifest)
            path.write_text(json.dumps({"context": 200}))
            with self.assertRaisesRegex(ValueError, "frozen suite input changed"):
                validate_pins(manifest)


if __name__ == "__main__":
    unittest.main()
