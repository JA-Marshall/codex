"""Project legacy evaluator evidence without changing its launch-lock authority."""

from pathlib import Path
import re

from terminal_run import RunSnapshot
from workflows.contracts import RunResult, fingerprint


class LegacyWorkflowAdapter:
    def collect(self, record, directory, run):
        workflow, stop, candidate, accepted = "unknown", "unconfirmed", None, None
        evaluation = "not_run" if record["evaluation_exit_code"] is None else "failed"
        evidence = {}
        try:
            snapshot = RunSnapshot(run)
            events = snapshot.journal("events.jsonl")
            if events and events[-1].get("state") in ("completed", "failed"):
                workflow = events[-1]["state"]
                evidence["workflow_journal_sha256"] = snapshot.hashes["events.jsonl"]
        except (OSError, ValueError, TypeError, KeyError) as error:
            evidence["workflow_error"] = str(error)
        if record["evaluation_exit_code"] == 0:
            try:
                snapshot = RunSnapshot(Path(directory) / "evaluation")
                result = snapshot.json("evaluation.json")
                observation = snapshot.json("observation.json")
                if not isinstance(result, dict) or not isinstance(observation, dict):
                    raise ValueError("evaluator artifacts must be objects")
                if (
                    type(result.get("schema_version")) is not int
                    or result["schema_version"] != 1
                    or result.get("fixture") != record["fixture"]
                    or result.get("fixture_commit") != record["repository_commit"]
                ):
                    raise ValueError("evaluator does not match the task and baseline")
                sources = observation.get("source_artifact_sha256")
                if (
                    not isinstance(sources, dict)
                    or sources.get("events.jsonl")
                    != evidence.get("workflow_journal_sha256")
                    or not evidence.get("workflow_journal_sha256")
                ):
                    raise ValueError(
                        "evaluator observation has a stale or missing workflow journal"
                    )
                if (
                    observation.get("schema_version") != 1
                    or observation.get("all_started_phases_shutdown") is not True
                    or Path(observation["run"]).resolve() != Path(run).resolve()
                    or Path(observation["repository"]).resolve()
                    != Path(record["repository"]).resolve()
                    or observation.get("workflow_state") != workflow
                ):
                    raise ValueError("evaluator lacks matching terminal observation")
                stop = "confirmed"
                files = result.get("candidate_files")
                if (
                    not isinstance(files, dict)
                    or not files
                    or any(
                        not isinstance(name, str)
                        or not name
                        or not isinstance(value, str)
                        or re.fullmatch(r"[a-f0-9]{64}", value) is None
                        for name, value in files.items()
                    )
                    or any(
                        type(result.get(name)) is not bool
                        for name in (
                            "task_success",
                            "public_test_success",
                            "hidden_test_success",
                        )
                    )
                ):
                    raise ValueError("invalid evaluator candidate or acceptance")
                if result["task_success"] and not (
                    result["public_test_success"] and result["hidden_test_success"]
                ):
                    raise ValueError("acceptance conflicts with evaluator checks")
                candidate = fingerprint(files)
                accepted = result["task_success"]
                evaluation = "completed"
                evidence["evaluation_artifacts_sha256"] = dict(snapshot.hashes)
            except (OSError, ValueError, TypeError, KeyError) as error:
                evidence["evaluation_error"] = str(error)
        if record.get("legacy_meter_sha256") is not None:
            try:
                snapshot = RunSnapshot(Path(directory) / "legacy-meter")
                meter = snapshot.json("result.json")
                if (
                    snapshot.hashes["result.json"] != record["legacy_meter_sha256"]
                    or meter.get("provider_handlers_stopped") is not True
                    or meter.get("namespace_stopped") is not True
                ):
                    raise ValueError("legacy meter lacks matching shutdown evidence")
                evidence["legacy_meter"] = meter
                evidence["legacy_meter_sha256"] = snapshot.hashes["result.json"]
            except (OSError, ValueError, TypeError, KeyError) as error:
                evidence["meter_error"] = str(error)
                stop, evaluation, candidate, accepted = (
                    "unconfirmed",
                    "failed",
                    None,
                    None,
                )
        return RunResult(
            record["run_id"],
            record["workflow"],
            record["fixture"],
            workflow,
            stop,
            evaluation,
            candidate,
            accepted,
            evidence,
        )
