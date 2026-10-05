"""Small legacy-compatible contracts; execution policy stays with the adapter."""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Protocol


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class StudySpec:
    campaign_id: str
    inputs_sha256: str
    requested_model: str | None
    trial_count: int
    schema_version: int = 1
    adapter: str = "legacy-v1"

    @classmethod
    def from_campaign(cls, manifest):
        trials = manifest.get("trials")
        if (
            manifest.get("schema_version") != 1
            or not isinstance(manifest.get("campaign_id"), str)
            or not manifest["campaign_id"]
            or not isinstance(trials, list)
            or not 1 <= len(trials) <= 1000
            or len({entry["run_id"] for entry in trials}) != len(trials)
        ):
            raise ValueError("invalid study campaign identity or trial matrix")
        # The existing frozen manifest remains the authority for all input pins,
        # budgets, concurrency, and policy. Exclude only the loader's own digest.
        inputs = {
            key: value for key, value in manifest.items() if key != "manifest_sha256"
        }
        return cls(
            manifest["campaign_id"],
            fingerprint(inputs),
            manifest.get("requested_model"),
            len(trials),
        )


@dataclass(frozen=True)
class RunResult:
    run_id: str
    workflow: str
    task_id: str
    workflow_status: str
    stop_status: str
    evaluation_status: str
    candidate_sha256: str | None
    task_success: bool | None
    evidence: dict
    schema_version: int = 1

    def __post_init__(self):
        if (
            self.workflow_status not in ("completed", "failed", "unknown")
            or self.stop_status not in ("confirmed", "unconfirmed")
            or self.evaluation_status not in ("completed", "failed", "not_run")
            or (self.task_success is not None and type(self.task_success) is not bool)
        ):
            raise ValueError("invalid workflow result status")
        if self.evaluation_status == "completed":
            if self.stop_status != "confirmed" or self.candidate_sha256 is None:
                raise ValueError(
                    "acceptance requires stopped, identified, evaluated candidate"
                )
        elif self.task_success is not None:
            raise ValueError("unevaluated task acceptance must remain unknown")

    def to_dict(self):
        return asdict(self)


class WorkflowAdapter(Protocol):
    """Normalize evidence after execution; never grant permission to grade."""

    def collect(self, record: dict, directory, run) -> RunResult: ...
