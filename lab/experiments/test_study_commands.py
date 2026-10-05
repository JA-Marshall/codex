import json
from pathlib import Path
import sys
import tempfile
import unittest

from campaign_inputs import digest, load_campaign, write_json
from study import run_once
from study_ledger import register_variant
from study_resume import prepare_resume


class StudyCommandsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "parent"
        archive = self.output / "inputs/lab"
        (archive / "experiments").mkdir(parents=True)
        runner = archive / "experiments/run_campaign.py"
        runner.write_text(
            "import json,sys\nfrom pathlib import Path\np=Path(sys.argv[2]); m=json.loads(p.read_text()); (p.parent/'results.json').write_text(json.dumps({'campaign_id':m['campaign_id'],'trials':[]}))\n"
        )
        self.path = self.output / "campaign.json"
        self.trials = [
            dict(
                run_id=f"trial-{index:04}",
                fixture="durable-queue-v1",
                workflow="test",
                repetition=1,
            )
            for index in (1, 2)
        ]
        self.manifest = dict(
            schema_version=1,
            campaign_id="parent",
            approval="campaign_delegated",
            jobs=1,
            max_amendments=0,
            automatic_retries=0,
            resume_supported=False,
            output=str(self.output),
            archive=str(archive),
            python=sys.executable,
            trials=self.trials,
            pins={str(runner): digest(runner)},
        )
        write_json(self.path, self.manifest)

    def terminal(self, *, started_pending=False, confirmed=True):
        events = [dict(type="trial_started", run_id="trial-0001")]
        if started_pending:
            events.append(dict(type="trial_started", run_id="trial-0002"))
        events.append(dict(type="campaign_finished"))
        (self.output / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events)
        )
        records = [
            dict(
                self.trials[0],
                status="finished",
                workflow_result=dict(
                    stop_status="confirmed" if confirmed else "unknown",
                    evidence={"runtime": {"provider_handlers_stopped": True}},
                ),
            ),
            dict(self.trials[1], status="not_started"),
        ]
        write_json(
            self.output / "results.json", dict(campaign_id="parent", trials=records)
        )

    def test_run_records_exit_and_refuses_duplicate_attempt(self):
        self.assertEqual(run_once(self.path), 0)
        receipts = [
            json.loads(path.read_text())
            for path in sorted((self.output / "study-attempts").glob("*.json"))
        ]
        self.assertEqual(
            [row["kind"] for row in receipts], ["started", "process_exited"]
        )
        self.assertIsNotNone(receipts[-1]["results_sha256"])
        with self.assertRaises(FileExistsError):
            run_once(self.path)

    def test_resume_only_never_started_slots_preserves_pins_and_parent_scores(self):
        self.terminal()
        original = (self.output / "results.json").read_bytes()
        child_path = prepare_resume(self.path, self.root / "child")
        child = load_campaign(child_path)
        self.assertEqual(child["trials"], [self.trials[1]])
        self.assertEqual(
            list(child["pins"].values()), list(self.manifest["pins"].values())
        )
        self.assertEqual((self.output / "results.json").read_bytes(), original)
        self.assertFalse(child["resume_supported"])
        with self.assertRaises(FileExistsError):
            prepare_resume(self.path, self.root / "duplicate")

    def test_resume_rejects_started_trial_even_if_result_says_unstarted(self):
        self.terminal(started_pending=True)
        with self.assertRaisesRegex(ValueError, "previously started"):
            prepare_resume(self.path, self.root / "child")
        self.assertFalse((self.root / "child").exists())

    def test_resume_requires_confirmed_shutdown_for_started_trials(self):
        self.terminal(confirmed=False)
        with self.assertRaisesRegex(ValueError, "confirmed shutdown"):
            prepare_resume(self.path, self.root / "child")

    def test_legacy_resume_revalidates_observation_and_source_hashes(self):
        self.check_legacy_resume(False)

    def test_metered_legacy_resume_revalidates_private_run_path_and_meter_hash(self):
        self.check_legacy_resume(True)

    def check_legacy_resume(self, metered):
        from workflows.legacy import LegacyWorkflowAdapter

        self.terminal()
        trial = self.output / "trials/trial-0001"
        run = (
            trial / "legacy-meter/runs/trial-0001"
            if metered
            else self.output / "runs/trial-0001"
        )
        if metered:
            self.manifest["legacy_runtime"] = {"budget": {"requests": 120}}
            write_json(self.path, self.manifest)
        (trial / "evaluation").mkdir(parents=True)
        run.mkdir(parents=True)
        (run / "events.jsonl").write_text(
            json.dumps({"schema_version": 1, "sequence": 1, "state": "completed"})
            + "\n"
        )
        record = dict(
            self.trials[0],
            status="finished",
            repository=str(trial / "repository"),
            repository_commit="a" * 40,
            evaluation_exit_code=0,
        )
        write_json(
            trial / "evaluation/evaluation.json",
            dict(
                schema_version=1,
                fixture="durable-queue-v1",
                fixture_commit="a" * 40,
                candidate_files={"app.py": "b" * 64},
                task_success=True,
                public_test_success=True,
                hidden_test_success=True,
            ),
        )
        observation = dict(
            schema_version=1,
            source_artifact_sha256={"events.jsonl": digest(run / "events.jsonl")},
            all_started_phases_shutdown=True,
            workflow_state="completed",
            run=str(run),
            repository=record["repository"],
        )
        write_json(trial / "evaluation/observation.json", observation)
        if metered:
            meter_path = trial / "legacy-meter/result.json"
            write_json(
                meter_path,
                {"provider_handlers_stopped": True, "namespace_stopped": True},
            )
            record["legacy_meter_sha256"] = digest(meter_path)
        record["workflow_result"] = (
            LegacyWorkflowAdapter().collect(record, trial, run).to_dict()
        )
        self.assertEqual(record["workflow_result"]["stop_status"], "confirmed")
        result = json.loads((self.output / "results.json").read_text())
        result["trials"][0] = record
        write_json(self.output / "results.json", result)
        observation["all_started_phases_shutdown"] = False
        write_json(trial / "evaluation/observation.json", observation)
        with self.assertRaisesRegex(ValueError, "confirmed shutdown"):
            prepare_resume(self.path, self.root / "bad-child")
        observation["all_started_phases_shutdown"] = True
        write_json(trial / "evaluation/observation.json", observation)
        if metered:
            saved = meter_path.read_bytes()
            write_json(
                meter_path,
                {"provider_handlers_stopped": False, "namespace_stopped": True},
            )
            with self.assertRaisesRegex(ValueError, "confirmed shutdown"):
                prepare_resume(self.path, self.root / "bad-meter-child")
            meter_path.write_bytes(saved)
        child = load_campaign(prepare_resume(self.path, self.root / "legacy-child"))
        self.assertEqual(child["trials"], [self.trials[1]])

    def test_variant_is_immutable_and_parent_must_exist(self):
        registry = self.root / "variants"
        value = dict(
            id="lean-v1",
            parent=None,
            hypothesis="Fewer steps reduce cost.",
            change="One review pass.",
        )
        target = register_variant(registry, value, self.path)
        self.assertEqual(
            json.loads((target / "variant.json").read_text())["campaign_sha256"],
            digest(self.path),
        )
        with self.assertRaises(FileExistsError):
            register_variant(registry, value, self.path)
        with self.assertRaises(ValueError):
            register_variant(
                registry, dict(value, id="lean-v2", parent="unknown"), self.path
            )
        register_variant(
            registry, dict(value, id="lean-v2", parent="lean-v1"), self.path
        )


if __name__ == "__main__":
    unittest.main()
