import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from terminal_run import observe_terminal
from test_terminal_run import make_run, write_json, write_journal


class ScopeObservationTests(unittest.TestCase):
    def test_scope_is_bound_to_campaign_permissions_and_shutdown_evidence(self):
        for variant in ("valid", "missing_audit", "wrong_profile", "wide_profile", "missing_deny", "undeclared_deny", "wrong_digest", "late_bind", "unauthorized_complete"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                run = Path(directory) / "run"
                events = make_run(run, "completed")
                private = str(run.parent / "private")
                scope = {"schema_version": 1, "write_paths": ["src"], "deny_read_paths": [private], "read_paths": []}
                digest = hashlib.sha256(json.dumps(scope, separators=(",", ":")).encode()).hexdigest()
                write_json(run / "evidence/task-scope.json", {"scope": scope, "scope_sha256": digest})
                write_json(run / "evidence/campaign-policy.json", {"task_scope": scope})
                candidate = str(run.parent / "fixture/repository/src")
                scratch = str(run.parent / "scratch")
                writes = [candidate, scratch] + (["/"] if variant == "wide_profile" else [])
                profile = {"type": "managed", "network": "restricted", "file_system": {"type": "restricted", "entries": [
                    {"path": {"type": "path", "path": path}, "access": "write"} for path in writes]}}
                if variant != "missing_deny":
                    profile["file_system"]["entries"].append({"path": {"type": "path", "path": private}, "access": "deny"})
                permissions = {"scope_sha256": digest, "phase": "implementation", "candidate_write_paths": [candidate],
                               "deny_read_paths": [] if variant == "undeclared_deny" else [private],
                               "scratch": scratch, "permission_profile": profile}
                audit = {"scope_sha256": digest, "authorized": True, "candidate_unchanged": False}
                if variant == "unauthorized_complete":
                    audit["authorized"] = False
                binding = {"type": "task_scope_bound", "scope_sha256": digest}
                scope_events = [binding, events[0], {"type": "phase_scope_permissions", "epoch": 1, "evidence": permissions}, *events[1:-1],
                                {"type": "phase_scope_audit", "epoch": 1, "evidence": audit}, events[-1]]
                if variant == "missing_audit":
                    scope_events.pop(-2)
                elif variant == "late_bind":
                    scope_events[0], scope_events[1] = scope_events[1], scope_events[0]
                elif variant == "wrong_digest":
                    binding["scope_sha256"] = "0" * 64
                output_path = run / "evidence/phase-01.json"
                output = json.loads(output_path.read_text())
                output["task_scope"] = dict(permissions, audit=audit)
                output["events"][0]["msg"]["permission_profile"] = {"type": "disabled"} if variant == "wrong_profile" else profile
                write_json(output_path, output)
                write_journal(run / "runtime-events.jsonl", scope_events)
                if variant == "valid":
                    _, _, observed = observe_terminal(run)
                    self.assertEqual(observed["task_scope_sha256"], digest)
                else:
                    with self.assertRaises(ValueError):
                        observe_terminal(run)


if __name__ == "__main__":
    unittest.main()
