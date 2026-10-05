"""Small TOML study input over the existing campaign freezer."""

from dataclasses import asdict
import json
from pathlib import Path
import sys
import tomllib
from types import SimpleNamespace

from campaign_inputs import (
    delegated_catalog,
    digest,
    freeze,
    read_json,
    validate_measurement,
    write_json,
)
from study_storage import policy
from study_ledger import validate_variant
from task_registry import discover
from workflows.contracts import StudySpec


def load_study(path):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 65536:
        raise ValueError("study configuration exceeds64KiB")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    required = {"paths", "conditions", "storage", "stage"}
    if not required <= set(data) or set(data) - required - {
        "jobs",
        "repetitions",
        "max_amendments",
        "purpose",
        "variant",
        "legacy_budget",
    }:
        raise ValueError("study needs paths, conditions, storage and stage")
    if "variant" in data:
        if not isinstance(data["variant"], dict):
            raise ValueError("variant must be a table")
        data["variant"].setdefault("parent", None)
        validate_variant(data["variant"])
    if data["stage"] != "development":
        raise ValueError(
            "validation/confirmation stage remains gated; tuning cannot discover held-out packs"
        )
    paths = data["paths"]
    required_paths = {
        "binary",
        "codex_home",
        "catalog",
        "instruction_root",
        "sandbox",
        "output",
        "task_root",
        "provider_service",
    }
    optional_paths = {
        "sdk_config",
        "task_toolchain",
        "task_just",
        "python_runtime",
        "corpus_index",
    }
    if (
        not isinstance(paths, dict)
        or not required_paths <= set(paths)
        or set(paths) - required_paths - optional_paths
    ):
        raise ValueError("invalid study paths")
    resolved = {}
    for name in required_paths | optional_paths:
        value = paths.get(name)
        if value is None:
            resolved[name] = None
            continue
        if not isinstance(value, str) or not value:
            raise ValueError("study paths must be explicit strings")
        target = Path(value).expanduser()
        if not target.is_absolute():
            target = path.parent / target
        if (
            paths.get("corpus_index")
            and name in ("corpus_index", "task_root")
            and target.absolute() != target.resolve(strict=True)
        ):
            raise ValueError("corpus paths must not contain aliases")
        # Preserve multicall sandbox alias, as the existing freezer does.
        resolved[name] = (
            target.parent.resolve(strict=True) / target.name
            if name == "sandbox"
            else target.resolve(strict=name != "output")
        )
    if resolved["corpus_index"]:
        from corpus_manifest import bind_development

        bind_development(resolved["corpus_index"], resolved["task_root"])
    tasks = discover(resolved["task_root"], allowed_splits={"development"})
    conditions = data["conditions"]
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= 16:
        raise ValueError("study needs1..16 explicit conditions")
    pairs = set()
    for condition in conditions:
        if (
            not isinstance(condition, dict)
            or set(condition) != {"workflow", "tasks"}
            or not isinstance(condition["workflow"], str)
        ):
            raise ValueError("condition needs workflow and task IDs")
        selected = condition["tasks"]
        if (
            not isinstance(selected, list)
            or not selected
            or any(not isinstance(name, str) or name not in tasks for name in selected)
        ):
            raise ValueError("condition names unknown tasks")
        for name in selected:
            pair = (condition["workflow"], name)
            if pair in pairs:
                raise ValueError("duplicate study condition")
            pairs.add(pair)
    if resolved["corpus_index"]:
        bind_development(
            resolved["corpus_index"],
            resolved["task_root"],
            {name: tasks[name] for _, name in pairs},
        )
    stages = {
        "development": "development",
        "validation": "study",
        "confirmation": "confirmation",
    }
    if data["stage"] not in stages or any(
        tasks[name].manifest["split"] != stages[data["stage"]] for _, name in pairs
    ):
        raise ValueError("study stage cannot mix or silently tune held-out task splits")
    workflow_names = list(
        dict.fromkeys(condition["workflow"] for condition in conditions)
    )
    delegated_catalog(resolved["catalog"].read_text(encoding="utf-8"), workflow_names)
    sdk = read_json(resolved["sdk_config"], 65536) if resolved["sdk_config"] else None
    if sdk is not None:
        supported = {
            "direct-v1",
            "bmad-build-auto-v6.12.0",
            "bmad-orchestrated-v6.12.0-recipe1",
            "our-v0",
        }
        if not set(workflow_names) <= supported:
            raise ValueError("unsupported SDK workflow")
        for workflow, name in pairs:
            if tasks[name].manifest.get("track") == "B" and (
                workflow == "bmad-build-auto-v6.12.0"
                or sdk.get("project_recipe") != "stop-probe-followup-v1"
                or sdk.get("interaction_policy") != "delegated-task-v1"
            ):
                raise ValueError(
                    "Track B requires supported arm and explicit project/interaction recipe"
                )
    elif any(
        tasks[name].manifest.get("track") == "B"
        or "owner-clarification" in tasks[name].manifest.get("capabilities", [])
        for _, name in pairs
    ):
        raise ValueError("legacy owner/Track B capability has not been verified")
    if "legacy_budget" in data:
        from workflows.usage import Budget

        if sdk is not None:
            raise ValueError("legacy aggregate budget cannot override an SDK budget")
        Budget(**data["legacy_budget"])
    storage = policy(data["storage"])
    jobs, repetitions = data.get("jobs", 2), data.get("repetitions", 1)
    if (
        type(jobs) is not int
        or not 1 <= jobs <= 32
        or type(repetitions) is not int
        or not 1 <= repetitions <= 100
    ):
        raise ValueError("bounded jobs and repetitions required")
    if sdk is not None and jobs > 2:
        raise ValueError("SDK campaigns support at most two concurrent trials")
    validate_measurement(data.get("purpose", "throughput"), jobs)
    if (
        type(data.get("max_amendments", 0)) is not int
        or not 0 <= data.get("max_amendments", 0) <= 4
    ):
        raise ValueError("amendments must be an integer in0..4")
    selected_tasks = sorted({name for _, name in pairs})
    planned_ids, ordinal = [], 0
    for repetition in range(1, repetitions + 1):
        offset = (repetition - 1) % len(workflow_names)
        for name in selected_tasks:
            for workflow in workflow_names[offset:] + workflow_names[:offset]:
                ordinal += 1
                if (workflow, name) in pairs:
                    planned_ids.append(f"trial-{ordinal:04}")
    policy(storage, planned_ids)
    if (
        len(workflow_names) * len(selected_tasks) * repetitions > 1000
        or jobs * storage["reserve_per_active_trial"] > storage["max_bytes"]
    ):
        raise ValueError("matrix or storage reservation exceeds declared envelope")
    args = SimpleNamespace(
        **resolved,
        workflow=list(dict.fromkeys(condition["workflow"] for condition in conditions)),
        fixture=sorted({name for _, name in pairs}),
        repetitions=repetitions,
        jobs=jobs,
        max_amendments=data.get("max_amendments", 0),
        purpose=data.get("purpose", "throughput"),
    )
    return args, data, pairs


def freeze_study(path):
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        raise ValueError("campaign freeze requires Linux/Python3.12")
    args, data, pairs = load_study(path)
    corpus_bytes = args.corpus_index.read_bytes() if args.corpus_index else None
    manifest = freeze(args)
    source_path = Path(path).resolve(strict=True)
    frozen_source = Path(manifest["archive"]) / "study-input.toml"
    frozen_source.write_bytes(source_path.read_bytes())
    manifest["pins"][str(frozen_source)] = digest(frozen_source)
    if args.corpus_index:
        from corpus_manifest import bind_development

        if args.corpus_index.read_bytes() != corpus_bytes:
            raise ValueError("corpus index changed during freeze")
        corpus = bind_development(
            args.corpus_index,
            args.task_root,
            discover(manifest["task_root"], allowed_splits={"development"}),
        )
        if corpus != json.loads(corpus_bytes):
            raise ValueError("corpus metadata changed while binding archived inputs")
        frozen_index = Path(manifest["archive"]) / "corpus-index.json"
        frozen_index.write_bytes(corpus_bytes)
        manifest["pins"][str(frozen_index)] = digest(frozen_index)
        certificates = {}
        for name in sorted({name for _, name in pairs}):
            certificate = args.corpus_index.parent / "certificates" / (name + ".json")
            target = (
                Path(manifest["archive"]) / "corpus-certificates" / certificate.name
            )
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(certificate.read_bytes())
            if digest(target) != next(
                item["calibration_sha256"]
                for item in corpus["entries"]
                if item["id"] == name
            ):
                raise ValueError("certificate changed while freezing")
            certificate_data = json.loads(target.read_bytes())
            for field in ("evaluator_sha256", "calibration_driver_sha256"):
                if any(
                    digest(Path(manifest["archive"]) / "experiments" / module)
                    != expected
                    for module, expected in certificate_data[field].items()
                ):
                    raise ValueError(
                        "frozen evaluator or calibration driver differs from certificate"
                    )
            manifest["pins"][str(target)] = digest(target)
            certificates[name] = str(target)
        manifest["corpus"] = {
            "id": corpus["id"],
            "index": str(frozen_index),
            "index_sha256": digest(frozen_index),
            "certificates": certificates,
            "selected_ids": sorted({name for _, name in pairs}),
            "scope": "development only; opaque held-out metadata conveys no task access",
        }
    manifest["trials"] = [
        entry
        for entry in manifest["trials"]
        if (entry["workflow"], entry["fixture"]) in pairs
    ]
    manifest.update(
        study_stage=data["stage"],
        storage_policy=data["storage"],
        variant=data.get("variant"),
        disk_limit_semantics="admission ceiling plus declared in-flight reservations; not a filesystem quota",
        source_study_toml=str(Path(path).resolve()),
    )
    if "legacy_budget" in data:
        manifest["legacy_runtime"] = {
            "budget": data["legacy_budget"],
            "boundary": "original host in owned PID namespace, all phases share one provider ledger",
        }
    write_json(args.output / "campaign.json", manifest)
    write_json(args.output / "study.json", asdict(StudySpec.from_campaign(manifest)))
    return manifest
