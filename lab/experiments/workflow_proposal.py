"""Record a one-policy experiment proposal between already frozen development variants."""

import argparse
import json
from pathlib import Path
import uuid

from campaign_inputs import digest, load_campaign, read_json, write_json
from study_ledger import append_record
from task_registry import IDENTIFIER, relative_path


def propose_revision(revision_path, registry):
    attempt_id = uuid.uuid4().hex
    attempts = Path(registry) / "revision-attempts"
    append_record(
        attempts,
        "proposal_received",
        dict(attempt_id=attempt_id, revision_path=str(Path(revision_path).resolve())),
    )
    try:
        revision = read_json(revision_path, 65536)
        required = {
            "id",
            "hypothesis",
            "incumbent_manifest",
            "challenger_manifest",
            "policy_change",
        }
        if set(revision) != required or any(
            not isinstance(revision[key], str) or not 1 <= len(revision[key]) <= 4096
            for key in required - {"policy_change"}
        ):
            raise ValueError(
                "revision requires identity, hypothesis, two frozen manifests and one policy change"
            )
        paths = [
            Path(revision[key]).resolve(strict=True)
            for key in ("incumbent_manifest", "challenger_manifest")
        ]
        arms = [read_json(path) for path in paths]
        if paths[0] == paths[1] or any(
            arm.get("study_stage") != "development" or not arm.get("variant")
            for arm in arms
        ):
            raise ValueError(
                "two explicitly identified frozen development variants required"
            )
        # Inspect only public stage/task metadata before hashing frozen payloads.
        for arm in arms:
            for name in {row["fixture"] for row in arm["trials"]}:
                if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                    raise ValueError("invalid proposal task identity")
                manifest_path = relative_path(
                    Path(arm["task_root"]), name + "/manifest.json"
                )
                if read_json(manifest_path).get("split") != "development":
                    raise ValueError("held-out tasks cannot enter workflow tuning")
        arms = [load_campaign(path) for path in paths]
        if arms[0]["variant"]["id"] == arms[1]["variant"]["id"]:
            raise ValueError("incumbent and challenger must have distinct variant IDs")
        matrix = lambda arm: sorted(
            (row["fixture"], row["repetition"]) for row in arm["trials"]
        )
        if matrix(arms[0]) != matrix(arms[1]) or any(
            len({row["workflow"] for row in arm["trials"]}) != 1 for arm in arms
        ):
            raise ValueError(
                "proposal requires one arm each with matched task/repetition slots"
            )
        for name in (
            "requested_model",
            "provider_service",
            "jobs",
            "measurement_purpose",
            "phase_timeout_clock",
            "max_amendments",
            "automatic_retries",
            "hard_token_limit",
            "hard_spend_limit",
        ):
            if arms[0].get(name) != arms[1].get(name):
                raise ValueError("comparison setting differs: " + name)
        for name in (
            "pin",
            "dependency_versions",
            "budget",
            "reasoning_effort",
            "interaction_policy",
            "project_recipe",
            "bmad_source_sha256",
        ):
            if not all(arm.get("sdk_runtime") for arm in arms) or arms[0][
                "sdk_runtime"
            ].get(name) != arms[1]["sdk_runtime"].get(name):
                raise ValueError("SDK comparison setting differs: " + name)
        if digest(arms[0]["sdk_runtime"]["model_catalog"]) != digest(
            arms[1]["sdk_runtime"]["model_catalog"]
        ):
            raise ValueError("model catalogs differ")
        change = revision["policy_change"]
        if not isinstance(change, dict) or set(change) != {
            "path",
            "before_sha256",
            "after_sha256",
            "description",
        }:
            raise ValueError(
                "declare one policy source path, before/after hashes and description"
            )
        source = Path(change["path"])
        if (
            source.is_absolute()
            or ".." in source.parts
            or not source.as_posix().startswith("experiments/workflows/")
            or source.suffix != ".py"
        ):
            raise ValueError(
                "policy proposal must target a workflow adapter source file"
            )
        if (
            not isinstance(change["description"], str)
            or not 1 <= len(change["description"]) <= 4096
        ):
            raise ValueError("bounded policy-change description required")
        inventories = []
        for arm in arms:
            archive = Path(arm["archive"])
            inventories.append(
                {
                    Path(path).relative_to(archive).as_posix()
                    if Path(path).is_relative_to(archive)
                    else path: sha
                    for path, sha in arm["pins"].items()
                }
            )
        differences = {
            name
            for name in inventories[0].keys() | inventories[1].keys()
            if inventories[0].get(name) != inventories[1].get(name)
        } - {"study-input.toml"}
        if (
            differences != {source.as_posix()}
            or inventories[0].get(source.as_posix()) != change["before_sha256"]
            or inventories[1].get(source.as_posix()) != change["after_sha256"]
        ):
            raise ValueError(
                "frozen source difference does not match the declared single policy change"
            )
        proposal = dict(
            schema_version=1,
            revision=revision,
            attempt_id=attempt_id,
            arms=[
                dict(variant=arm["variant"], manifest=str(path), sha256=digest(path))
                for arm, path in zip(arms, paths)
            ],
            paired_slots=matrix(arms[0]),
            model_calls=0,
            status="proposed; no implicit launch",
            limitation="one changed source file is mechanically verified; semantic one-policy scope requires review",
        )
        destination = Path(registry) / "proposals" / attempt_id
        destination.mkdir(parents=True)
        write_json(destination / "proposal.json", proposal)
        append_record(
            attempts,
            "proposed",
            dict(
                attempt_id=attempt_id,
                proposal=str(destination / "proposal.json"),
                revision_sha256=digest(revision_path),
            ),
        )
        return destination / "proposal.json"
    except Exception as error:
        append_record(
            attempts, "rejected", dict(attempt_id=attempt_id, error=str(error)[:2048])
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    print(propose_revision(args.revision, args.registry))


if __name__ == "__main__":
    main()
