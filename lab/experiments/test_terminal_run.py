import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest

from evaluate_fixture import evaluate
from setup_fixture import FIXTURE, evaluator_fingerprint, setup
from terminal_run import observe_terminal


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def write_journal(path, events):
    path.write_text(
        "".join(
            json.dumps(dict(event, schema_version=1, sequence=index + 1)) + "\n"
            for index, event in enumerate(events)
        )
    )


def make_run(path, state="failed"):
    path.mkdir()
    write_journal(
        path / "events.jsonl",
        [{"state": state, "elapsed_ms": 10, "change": {"type": state}}],
    )
    events = [
        {"type": "phase_started", "epoch": 1, "phase": "implementation"},
        {"type": "phase_thread_bound", "epoch": 1, "thread_id": "test-thread"},
        {
            "type": "tool_admitted",
            "epoch": 1,
            "thread_id": "test-thread",
            "turn_id": "turn",
            "call_id": "call",
        },
        {"type": "tool_finished", "epoch": 1, "turn_id": "turn", "call_id": "call"},
        {"type": "phase_stopped", "epoch": 1},
    ]
    write_journal(path / "runtime-events.jsonl", events)
    write_json(path / "evidence/input-01.json", {})
    write_json(
        path / "evidence/phase-01.json",
        {
            "thread_id": "test-thread",
            "events": [
                {
                    "msg": {
                        "type": "session_configured",
                        "session_id": "test-thread",
                        "cwd": str(path.parent / "fixture/repository"),
                    }
                },
                {"msg": {"type": "shutdown_complete"}},
            ],
            "token_usage": {
                "total_token_usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cached_input_tokens": 5,
                }
            },
        },
    )
    write_json(path / "config/run-spec.json", {})
    return events


class TerminalTests(unittest.TestCase):
    def test_dropped_dispatch_allows_confirmed_failed_shutdown_without_authority(self):
        for revoked in (False, True):
            with (
                self.subTest(revoked=revoked),
                tempfile.TemporaryDirectory() as directory,
            ):
                run = Path(directory) / "run"
                events = make_run(run)
                tail = [{"type": "admission_revoked", "epoch": 1}] if revoked else []
                tail.extend(
                    [
                        {
                            "type": "dispatch_dropped",
                            "identity": "test-thread\0turn\0call",
                        },
                        events[-1],
                        {
                            "type": "runtime_failed",
                            "phase_retained": False,
                            "active_dispatches": 0,
                            "shutdown_confirmed": False,
                        },
                    ]
                )
                write_journal(run / "runtime-events.jsonl", events[:3] + tail)
                before = {
                    str(path): path.read_bytes()
                    for path in run.rglob("*")
                    if path.is_file()
                }
                snapshot, _, observation = observe_terminal(run)
                self.assertEqual(
                    {
                        key: observation[key]
                        for key in (
                            "workflow_state",
                            "phase_turns",
                            "tool_admissions",
                            "all_started_phases_shutdown",
                            "authority_restored",
                        )
                    },
                    {
                        "workflow_state": "failed",
                        "phase_turns": 1,
                        "tool_admissions": 1,
                        "all_started_phases_shutdown": True,
                        "authority_restored": False,
                    },
                )
                snapshot.verify_unchanged()
                self.assertEqual(
                    before,
                    {
                        str(path): path.read_bytes()
                        for path in run.rglob("*")
                        if path.is_file()
                    },
                )

    def test_dropped_dispatch_rejects_malformed_foreign_and_unmatched_identity(self):
        identities = [
            None,
            1,
            [],
            "",
            "test-thread",
            "test-thread\0turn",
            "test-thread\0turn\0call\0extra",
            "\0turn\0call",
            "test-thread\0\0call",
            "test-thread\0turn\0",
            "test-thread\0turn\0" + "x" * 513,
            "test-thread\0turn\0" + "é" * 257,
            "foreign-thread\0turn\0call",
            "test-thread\0other-turn\0call",
            "test-thread\0turn\0other-call",
        ]
        for identity in identities:
            with (
                self.subTest(identity=identity),
                tempfile.TemporaryDirectory() as directory,
            ):
                run = Path(directory) / "run"
                events = make_run(run)
                events[3] = {"type": "dispatch_dropped", "identity": identity}
                write_journal(run / "runtime-events.jsonl", events)
                with self.assertRaises(ValueError):
                    observe_terminal(run)

    def test_dropped_dispatch_cannot_replace_other_completion_or_shutdown_proof(self):
        for variant in (
            "missing_identity",
            "wrong_epoch",
            "no_admission",
            "before_thread",
            "after_finish",
            "duplicate_drop",
            "finish_after_drop",
            "after_stop",
            "other_active_call",
            "missing_stop",
            "missing_shutdown",
            "retained_phase",
            "active_dispatches",
        ):
            with (
                self.subTest(variant=variant),
                tempfile.TemporaryDirectory() as directory,
            ):
                run = Path(directory) / "run"
                original = make_run(run)
                drop = {
                    "type": "dispatch_dropped",
                    "identity": "test-thread\0turn\0call",
                }
                events = original[:3] + [drop, original[-1]]
                if variant == "missing_identity":
                    del drop["identity"]
                elif variant == "wrong_epoch":
                    drop["epoch"] = 2
                elif variant == "no_admission":
                    events.pop(2)
                elif variant == "before_thread":
                    events = [original[0], drop, *original[1:]]
                elif variant == "after_finish":
                    events.insert(3, original[3])
                elif variant == "duplicate_drop":
                    events.insert(4, dict(drop))
                elif variant == "finish_after_drop":
                    events.insert(4, original[3])
                elif variant == "after_stop":
                    events = original + [drop]
                elif variant == "other_active_call":
                    events.insert(3, dict(original[2], call_id="other-call"))
                elif variant == "missing_stop":
                    events.pop()
                elif variant == "missing_shutdown":
                    path = run / "evidence/phase-01.json"
                    output = json.loads(path.read_text())
                    output["events"].pop()
                    write_json(path, output)
                elif variant in ("retained_phase", "active_dispatches"):
                    events.append(
                        {
                            "type": "runtime_failed",
                            "phase_retained": variant == "retained_phase",
                            "active_dispatches": int(variant == "active_dispatches"),
                            "shutdown_confirmed": False,
                        }
                    )
                write_journal(run / "runtime-events.jsonl", events)
                with self.assertRaises(ValueError):
                    observe_terminal(run)

    def test_delegated_approval_is_not_reported_as_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            make_run(run)
            write_journal(
                run / "events.jsonl",
                [
                    {
                        "state": "implementing",
                        "change": {
                            "type": "delegated_approved",
                            "policy_sha256": "a" * 64,
                        },
                    },
                    {"state": "failed", "change": {"type": "failed"}},
                ],
            )
            _, _, observation = observe_terminal(run)
            self.assertEqual(
                (
                    observation["first_plan_human_approval"],
                    observation["delegated_plan_approvals"],
                ),
                (None, 1),
            )

    def test_evaluation_respects_repository_launch_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup(root / "fixture")
            repository = root / "fixture/repository"
            with (repository / ".git/codex-lab-launch.lock").open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    evaluate(
                        repository,
                        root / "codex-linux-sandbox",
                        root / "evaluation",
                        root / "fixture/fixture.json",
                    )
            self.assertFalse((root / "evaluation").exists())

    def test_terminal_snapshot_accepts_failure_and_detects_later_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for state in ("failed", "completed"):
                run = root / state
                events = make_run(run, state)
                if state == "failed":
                    events.append(
                        {
                            "type": "runtime_failed",
                            "phase_retained": False,
                            "active_dispatches": 0,
                            "shutdown_confirmed": False,
                        }
                    )
                    write_journal(run / "runtime-events.jsonl", events)
                snapshot, _, observation = observe_terminal(run)
                self.assertEqual(
                    (
                        observation["workflow_state"],
                        observation["phase_turns"],
                        observation["usage"],
                    ),
                    (
                        state,
                        1,
                        {
                            "input_tokens": 10,
                            "output_tokens": 2,
                            "cached_input_tokens": 5,
                        },
                    ),
                )
                snapshot.verify_unchanged()
                write_json(run / "evidence/input-01.json", {"changed": True})
                with self.assertRaisesRegex(ValueError, "changed"):
                    snapshot.verify_unchanged()

    def test_refuses_missing_shutdown_active_dispatches_and_malformed_artifacts(self):
        for variant in (
            "active",
            "missing_stop",
            "wrong_epoch",
            "active_call",
            "missing_artifact",
            "missing_shutdown",
            "foreign_thread",
            "extra_input",
            "gap",
            "partial",
            "symlink",
            "retained_phase",
        ):
            with (
                self.subTest(variant=variant),
                tempfile.TemporaryDirectory() as directory,
            ):
                run = Path(directory) / "run"
                events = make_run(run)
                if variant == "active":
                    write_journal(
                        run / "events.jsonl",
                        [
                            {
                                "state": "implementing",
                                "change": {"type": "human_approved"},
                            }
                        ],
                    )
                elif variant == "missing_stop":
                    write_journal(run / "runtime-events.jsonl", events[:-1])
                elif variant == "wrong_epoch":
                    events[-1]["epoch"] = 2
                    write_journal(run / "runtime-events.jsonl", events)
                elif variant == "active_call":
                    write_journal(run / "runtime-events.jsonl", events[:3] + events[4:])
                elif variant == "missing_artifact":
                    (run / "evidence/phase-01.json").unlink()
                elif variant in ("missing_shutdown", "foreign_thread"):
                    write_json(
                        run / "evidence/phase-01.json",
                        {
                            "thread_id": "foreign"
                            if variant == "foreign_thread"
                            else "test-thread",
                            "events": [],
                        },
                    )
                elif variant == "extra_input":
                    write_json(run / "evidence/input-02.json", {})
                elif variant == "gap":
                    path = run / "runtime-events.jsonl"
                    path.write_text(
                        path.read_text().replace('"sequence": 1', '"sequence": 99')
                    )
                elif variant == "partial":
                    path = run / "runtime-events.jsonl"
                    path.write_text(path.read_text().rstrip())
                elif variant == "symlink":
                    path = run / "evidence/phase-01.json"
                    path.unlink()
                    path.symlink_to(run / "config/run-spec.json")
                elif variant == "retained_phase":
                    events.append(
                        {
                            "type": "runtime_failed",
                            "phase_retained": True,
                            "active_dispatches": 0,
                        }
                    )
                    write_journal(run / "runtime-events.jsonl", events)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    observe_terminal(run)

    def test_failed_run_evaluation_is_independent_and_preserves_journals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = setup(root / "fixture")
            repository = root / "fixture/repository"
            sandbox = root / "codex-linux-sandbox"
            sandbox.symlink_to(Path(os.environ["CODEX_LAB_TEST_BINARY"]).resolve())
            run = root / "run"
            make_run(run)
            write_json(
                run / "config/run-spec.json",
                {
                    "repository": {"commit": metadata["commit"]},
                    "task": (FIXTURE / "task.txt").read_text(),
                },
            )
            before = {str(p): p.read_bytes() for p in run.rglob("*") if p.is_file()}
            result = evaluate(
                repository,
                sandbox,
                root / "evaluation",
                root / "fixture/fixture.json",
                run,
            )
            self.assertFalse(result["task_success"])
            observation = json.loads((root / "evaluation/observation.json").read_text())
            self.assertEqual(observation["workflow_state"], "failed")
            self.assertEqual(observation["git"]["files_changed"], 0)
            self.assertEqual(
                before, {str(p): p.read_bytes() for p in run.rglob("*") if p.is_file()}
            )
            other = setup(root / "other")
            with self.assertRaisesRegex(ValueError, "run belongs to another"):
                evaluate(
                    Path(other["repository"]),
                    sandbox,
                    root / "wrong-repo",
                    root / "other/fixture.json",
                    run,
                )
            self.assertFalse((root / "wrong-repo").exists())
            old_metadata = copy.deepcopy(metadata)
            old_metadata["evaluator_sha256"] = "0" * 64
            write_json(root / "fixture/fixture.json", old_metadata)
            with self.assertRaisesRegex(ValueError, "explicitly pin"):
                evaluate(
                    repository,
                    sandbox,
                    root / "refused",
                    root / "fixture/fixture.json",
                    run,
                )
            self.assertFalse((root / "refused").exists())
            revised = evaluate(
                repository,
                sandbox,
                root / "revised",
                root / "fixture/fixture.json",
                run,
                evaluator_sha256=evaluator_fingerprint(),
            )
            self.assertEqual(revised["fixture_evaluator_sha256"], "0" * 64)
            self.assertFalse(revised["task_success"])
            self.assertEqual(
                before, {str(p): p.read_bytes() for p in run.rglob("*") if p.is_file()}
            )


if __name__ == "__main__":
    unittest.main()
