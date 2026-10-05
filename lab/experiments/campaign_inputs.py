"""Freeze a finite delegated campaign before any task checkout or model call."""

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib
import uuid

from fixture_registry import FIXTURES
from campaign_service import freeze_service
from campaign_tasks import (
    archive_just,
    archive_tasks,
    just_helper,
    selections,
    toolchain_pins,
)
from campaign_python import freeze_python_runtime, validate_python_runtime
from dataclasses import asdict
from workflows.contracts import StudySpec

MAX_RUNS = 1000
FIXTURE_NAMES = (*FIXTURES, "durable-queue-v1")


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_json(path, limit=8 * 1024 * 1024):
    with Path(path).open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("campaign JSON exceeds size limit")
    return json.loads(data)


def delegated_catalog(text, workflows):
    original = tomllib.loads(text)
    expected = copy.deepcopy(original)
    for name in workflows:
        if name not in original.get("workflows", {}):
            raise ValueError("unknown workflow: " + name)
        visited, current, approval = set(), name, None
        while current is not None:
            if current in visited or current not in original["workflows"]:
                raise ValueError("invalid workflow inheritance")
            visited.add(current)
            profile = original["workflows"][current]
            approval = approval or profile.get("approval")
            current = profile.get("extends")
        if approval not in ("human_required", "campaign_delegated"):
            raise ValueError("workflow must declare an approval policy")
    for profile in expected["workflows"].values():
        if profile.get("approval") == "human_required":
            profile["approval"] = "campaign_delegated"
    changed = re.sub(
        r"(?m)^(\s*approval\s*=\s*)([\"\x27])human_required\2(\s*(?:#.*)?)$",
        lambda match: match[1] + match[2] + "campaign_delegated" + match[2] + match[3],
        text,
    )
    if tomllib.loads(changed) != expected:
        raise ValueError("catalog approval declarations need ordinary TOML assignments")
    return changed, original


def freeze(args):
    purpose = getattr(args, "purpose", "throughput")
    validate_measurement(purpose, args.jobs)
    workflows, fixtures = args.workflow, args.fixture
    tasks, toolchain = selections(args, FIXTURE_NAMES)
    python_metadata, python_files = freeze_python_runtime(
        getattr(args, "python_runtime", None)
    )
    task_just = just_helper(args, tasks)
    count = len(workflows) * len(fixtures) * args.repetitions
    if (
        not 1 <= count <= MAX_RUNS
        or not 1 <= args.jobs <= 32
        or not 0 <= args.max_amendments <= 4
        or len(set(workflows)) != len(workflows)
        or len(set(fixtures)) != len(fixtures)
    ):
        raise ValueError(
            "require 1..1000 trials, jobs 1..32, amendments 0..4, unique selections"
        )
    binary, home, instruction_root = (
        path.resolve(strict=True)
        for path in (args.binary, args.codex_home, args.instruction_root)
    )
    # argv[0] selects the sandbox entry point in the multicall binary. Resolve
    # the parent, but retain the alias name even when it targets codex-lab.
    sandbox = args.sandbox.parent.resolve(strict=True) / args.sandbox.name
    if not sandbox.is_file():
        raise ValueError("sandbox executable does not exist")
    catalog = args.catalog.resolve(strict=True)
    effective, parsed = delegated_catalog(
        catalog.read_text(encoding="utf-8"), workflows
    )
    config_file = home / "config.toml"
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    service, service_pins = freeze_service(
        getattr(args, "provider_service", None), config
    )
    source = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    protected = (source, home, instruction_root, binary, sandbox, catalog)
    if tasks:
        protected += (Path(args.task_root).resolve(),)
    if toolchain:
        protected += (toolchain,)
    if task_just:
        protected += (task_just,)
    if python_metadata:
        protected += (Path(python_metadata["python_runtime"]["root"]),)
    if output.exists() or any(
        output.is_relative_to(p) or p.is_relative_to(output) for p in protected
    ):
        raise ValueError("output exists or overlaps campaign inputs")
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "inputs/lab"
    archive.mkdir(parents=True)
    for name in ("experiments", "fixtures"):
        shutil.copytree(
            source / name,
            archive / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for skill in parsed.get("skills", {}).values():
        relative = Path(skill["path"])
        origin = (instruction_root / relative).resolve(strict=True)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not origin.is_relative_to(instruction_root)
        ):
            raise ValueError("instruction path must stay inside instruction root")
        if digest(origin / "SKILL.md") != skill["sha256"]:
            raise ValueError("instruction digest does not match catalog")
        shutil.copytree(origin, archive / relative, dirs_exist_ok=True)
    frozen_catalog = archive / "campaign-workflows.toml"
    frozen_catalog.write_text(effective, encoding="utf-8")
    task_metadata = archive_tasks(archive, tasks)
    helper_metadata = archive_just(archive, task_just)
    pins = [binary, sandbox, config_file, Path(sys.executable).resolve()]
    if config.get("model_catalog_json"):
        model_catalog = Path(config["model_catalog_json"])
        pins.append((home / model_catalog).resolve(strict=True))
    bundled_sandbox = binary.parent / "codex-resources/bwrap"
    if bundled_sandbox.is_file():
        pins.append(bundled_sandbox)
    pins.extend(path for path in archive.rglob("*") if path.is_file())
    pins.extend(toolchain_pins(toolchain))
    pins.extend(python_files)
    trials = []
    for repetition in range(1, args.repetitions + 1):
        for fixture_name in fixtures:
            # Rotate workflow order across repetitions to spread ordering effects.
            offset = (repetition - 1) % len(workflows)
            for workflow in workflows[offset:] + workflows[:offset]:
                trials.append(
                    {
                        "run_id": f"trial-{len(trials) + 1:04}",
                        "fixture": fixture_name,
                        "workflow": workflow,
                        "repetition": repetition,
                        **(
                            tasks[fixture_name].facets()
                            if fixture_name in tasks
                            else {}
                        ),
                    }
                )
    manifest = {
        "schema_version": 1,
        "campaign_id": "campaign-" + uuid.uuid4().hex,
        "output": str(output),
        "archive": str(archive),
        "binary": str(binary),
        "sandbox": str(sandbox),
        "codex_home": str(home),
        "catalog": str(frozen_catalog),
        "python": str(Path(sys.executable).resolve()),
        **python_metadata,
        "requested_model": config.get("model"),
        "provider_service": service,
        **task_metadata,
        **helper_metadata,
        **({"task_toolchain": str(toolchain)} if toolchain else {}),
        "jobs": args.jobs,
        "measurement_purpose": purpose,
        "phase_timeout_clock": "wall_clock_including_provider_queue",
        "max_amendments": args.max_amendments,
        "trials": trials,
        "automatic_retries": 0,
        "hard_token_limit": None,
        "hard_spend_limit": None,
        "approval": "campaign_delegated",
        "resume_supported": False,
        "pins": {
            **{str(path): digest(path) for path in sorted(set(pins))},
            **service_pins,
        },
        "original_catalog_sha256": digest(catalog),
    }
    if getattr(args, "sdk_config", None) is not None:
        from workflows.sdk_freeze import freeze_sdk

        freeze_sdk(manifest, args.sdk_config)
    study = StudySpec.from_campaign(manifest)
    write_json(output / "study.json", asdict(study))
    write_json(output / "campaign.json", manifest)
    return manifest


def validate_pins(manifest):
    validate_python_runtime(manifest)
    for name, expected in manifest["pins"].items():
        if digest(name) != expected:
            raise ValueError("frozen campaign input changed: " + name)


def validate_measurement(purpose, jobs):
    if purpose not in ("throughput", "isolated-timing"):
        raise ValueError("unknown measurement purpose")
    if purpose == "isolated-timing" and jobs != 1:
        raise ValueError(
            "isolated-timing requires jobs=1; parallel runs measure shared throughput"
        )


def load_campaign(path, expected_digest=None):
    path = path.resolve(strict=True)
    fingerprint = digest(path)
    if expected_digest is not None and fingerprint != expected_digest:
        raise ValueError("campaign manifest changed after scheduling")
    manifest = read_json(path)
    validate_measurement(
        manifest.get("measurement_purpose", "throughput"), manifest.get("jobs")
    )
    if (
        manifest.get("phase_timeout_clock", "wall_clock_including_provider_queue")
        != "wall_clock_including_provider_queue"
    ):
        raise ValueError("unsupported phase timeout clock")
    trials = manifest.get("trials")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("approval") != "campaign_delegated"
        or type(manifest.get("jobs")) is not int
        or not 1 <= manifest["jobs"] <= 32
        or type(manifest.get("max_amendments")) is not int
        or not 0 <= manifest["max_amendments"] <= 4
        or not isinstance(trials, list)
        or not 1 <= len(trials) <= MAX_RUNS
        or manifest.get("automatic_retries") != 0
        or manifest.get("resume_supported") is not False
    ):
        raise ValueError("invalid bounded campaign manifest")
    if (
        Path(manifest["output"]).resolve() != path.parent
        or Path(manifest["archive"]).resolve() != path.parent / "inputs/lab"
    ):
        raise ValueError("campaign output and archive must match manifest directory")
    ids = set()
    for entry in trials:
        name = entry["run_id"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name)
            or name in ids
            or entry["fixture"] not in (*FIXTURE_NAMES, *manifest.get("task_ids", []))
            or not isinstance(entry["workflow"], str)
        ):
            raise ValueError("invalid or duplicate campaign trial")
        ids.add(name)
    if manifest.get("task_ids"):
        if Path(manifest["task_root"]).resolve() != path.parent / "inputs/lab/tasks":
            raise ValueError("task archive must belong to the frozen campaign")
    if any(entry.get("language") == "rust" for entry in trials):
        helper = path.parent / "inputs/lab/task-tools/just"
        if (
            manifest.get("task_just") != str(helper)
            or str(helper) not in manifest["pins"]
        ):
            raise ValueError("Rust task helper must be pinned in the frozen campaign")
    validate_pins(manifest)
    manifest["manifest_sha256"] = fingerprint
    return manifest
