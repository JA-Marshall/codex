import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluate_fixture import evaluate
from setup_fixture import setup
from test_terminal_run import make_run, write_json
from terminal_run import observe_terminal
from workflows.contracts import RunResult, StudySpec
from workflows.legacy import LegacyWorkflowAdapter


class WorkflowContractTests(unittest.TestCase):
    def test_evaluator_task_baseline_and_journal_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            make_run(run)
            _, _, observation = observe_terminal(run)
            record = dict(
                run_id="run",
                fixture="task",
                workflow="legacy",
                repository=observation["repository"],
                repository_commit="a" * 40,
                evaluation_exit_code=0,
            )
            result = dict(
                schema_version=1,
                fixture="task",
                fixture_commit="a" * 40,
                candidate_files={"a.py": "a" * 64},
                task_success=True,
                public_test_success=True,
                hidden_test_success=True,
            )
            adapter = LegacyWorkflowAdapter()
            write_json(root / "evaluation/observation.json", observation)
            write_json(root / "evaluation/evaluation.json", result)
            self.assertTrue(adapter.collect(record, root, run).task_success)
            for change in (
                {"fixture": "another-task"},
                {"fixture_commit": "b" * 40},
                {"schema_version": 2},
            ):
                write_json(root / "evaluation/evaluation.json", dict(result, **change))
                self.assertEqual(
                    adapter.collect(record, root, run).evaluation_status, "failed"
                )
            write_json(root / "evaluation/evaluation.json", result)
            observation["source_artifact_sha256"]["events.jsonl"] = "c" * 64
            write_json(root / "evaluation/observation.json", observation)
            self.assertIsNone(adapter.collect(record, root, run).task_success)

    def test_active_run_never_reaches_grading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            setup(root / "fixture")
            run = root / "run"
            make_run(run, state="implementing")
            with patch("evaluate_fixture.observe") as execute:
                with self.assertRaisesRegex(ValueError, "not terminal"):
                    evaluate(
                        root / "fixture/repository",
                        root / "codex-linux-sandbox",
                        root / "evaluation",
                        root / "fixture/fixture.json",
                        run,
                    )
            execute.assert_not_called()
            self.assertFalse((root / "evaluation").exists())

    def test_study_binds_policy_and_rejects_foreign_versions_and_duplicate_trials(self):
        manifest = dict(
            schema_version=1,
            campaign_id="study",
            pins={},
            trials=[dict(run_id="one")],
            max_amendments=0,
        )
        original = StudySpec.from_campaign(manifest)
        self.assertEqual(
            original, StudySpec.from_campaign(dict(manifest, manifest_sha256="loader"))
        )
        self.assertNotEqual(
            original.inputs_sha256,
            StudySpec.from_campaign(dict(manifest, max_amendments=1)).inputs_sha256,
        )
        for changes in ({"schema_version": 2}, {"trials": manifest["trials"] * 2}):
            with self.assertRaises(ValueError):
                StudySpec.from_campaign(dict(manifest, **changes))

    def test_unknown_evaluation_cannot_become_acceptance(self):
        unknown = RunResult(
            "run",
            "workflow",
            "task",
            "completed",
            "confirmed",
            "completed",
            "a" * 64,
            None,
            {"missing_owner_evidence": True},
        )
        self.assertIsNone(unknown.to_dict()["task_success"])
        with self.assertRaises(ValueError):
            RunResult(
                "run",
                "workflow",
                "task",
                "completed",
                "unconfirmed",
                "completed",
                None,
                True,
                {},
            )
        with self.assertRaises(ValueError):
            RunResult(
                "run",
                "workflow",
                "task",
                "failed",
                "confirmed",
                "failed",
                "a" * 64,
                False,
                {},
            )

    def test_compact_terminal_survives_missing_diagnostics_but_not_missing_shutdown(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            make_run(run)
            path = run / "evidence/phase-01.json"
            output = json.loads(path.read_text())
            configured = output["events"][0]["msg"]
            configured.pop("type")
            output.update(
                events=[],
                diagnostics_truncated=True,
                terminal=dict(
                    schema_version=1,
                    shutdown_confirmed=True,
                    session_configured=configured,
                ),
            )
            write_json(path, output)
            snapshot, _, observed = observe_terminal(run)
            self.assertTrue(observed["all_started_phases_shutdown"])
            snapshot.verify_unchanged()
            for change in (
                {"shutdown_confirmed": False},
                {"schema_version": 2},
                {"session_configured": dict(configured, session_id="foreign")},
            ):
                damaged = copy.deepcopy(output)
                damaged["terminal"].update(change)
                write_json(path, damaged)
                with self.assertRaises(ValueError):
                    observe_terminal(run)
            write_json(path, output)
            journal = run / "runtime-events.jsonl"
            journal.write_text("\n".join(journal.read_text().splitlines()[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "missing phase shutdown"):
                observe_terminal(run)

    def test_grader_crash_and_foreign_observation_remain_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            make_run(run, state="completed")
            record = dict(
                run_id="run",
                fixture="task",
                workflow="legacy",
                repository=str(root / "fixture/repository"),
                evaluation_exit_code=9,
            )
            adapter = LegacyWorkflowAdapter()
            result = adapter.collect(record, root, run)
            self.assertEqual(
                (
                    result.workflow_status,
                    result.stop_status,
                    result.evaluation_status,
                    result.task_success,
                ),
                ("completed", "unconfirmed", "failed", None),
            )
            record["evaluation_exit_code"] = 0
            write_json(
                root / "evaluation/evaluation.json",
                dict(
                    candidate_files={"a.py": "a" * 64},
                    task_success=True,
                    public_test_success=True,
                    hidden_test_success=True,
                ),
            )
            write_json(
                root / "evaluation/observation.json",
                dict(
                    run=str(root / "another-run"),
                    repository=record["repository"],
                    workflow_state="completed",
                    all_started_phases_shutdown=True,
                ),
            )
            result = adapter.collect(record, root, run)
            self.assertEqual(
                (result.stop_status, result.evaluation_status, result.task_success),
                ("unconfirmed", "failed", None),
            )
            for name in ("evaluation.json", "observation.json"):
                write_json(root / "evaluation" / name, [])
                result = adapter.collect(record, root, run)
                self.assertEqual(
                    (result.evaluation_status, result.task_success), ("failed", None)
                )
            (run / "events.jsonl").write_text("[]\n")
            self.assertEqual(
                adapter.collect(record, root, run).workflow_status, "unknown"
            )


if __name__ == "__main__":
    unittest.main()
