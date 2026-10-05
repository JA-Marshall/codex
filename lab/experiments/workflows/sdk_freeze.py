"""Freeze SDK-specific inputs into the existing campaign archive."""

from dataclasses import asdict
import importlib.metadata
from pathlib import Path
import shutil
import sys
import tomllib

from campaign_inputs import digest, read_json
from workflows.bmad_install import BmadPackage, package_digest


def freeze_sdk(manifest, settings_path):
    settings = read_json(settings_path, 65536)
    from workflows.interaction_policy import DELEGATED_TASK

    interaction_policy = settings.get("interaction_policy")
    if interaction_policy not in (None, DELEGATED_TASK):
        raise ValueError("unsupported shared interaction policy")
    project_recipe = settings.get("project_recipe")
    if project_recipe not in (None, "stop-probe-followup-v1"):
        raise ValueError("unsupported evolving project recipe")
    arms = {entry["workflow"] for entry in manifest["trials"]}
    if (
        not arms
        <= {
            "direct-v1",
            "bmad-build-auto-v6.12.0",
            "bmad-orchestrated-v6.12.0-recipe1",
            "our-v0",
        }
        or manifest["jobs"] > 2
        or not manifest.get("provider_service")
        or not manifest.get("task_ids")
    ):
        raise ValueError(
            "SDK compatibility requires supported arms, repository tasks, shared service, and at most two trials concurrently"
        )
    source = Path(settings["sdk_source"]).resolve(strict=True)
    sys.path.insert(0, str(source))
    from workflows.session_process import RuntimePin
    from workflows.usage import Budget

    pin = RuntimePin.capture(manifest["binary"], settings["source_commit"])
    budget = Budget(**settings["budget"])
    profile = tomllib.loads((Path(manifest["codex_home"]) / "config.toml").read_text())
    effort = profile.get("model_reasoning_effort")
    if effort not in ("minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("SDK campaign requires an explicit supported reasoning effort")
    archive = Path(manifest["archive"])
    copied = archive / "sdk-python"
    shutil.copytree(
        source, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    dependencies = archive / "sdk-dependencies"
    dependencies.mkdir()
    versions = {}
    # Supply only the matching SDK's Python dependencies. Never install/use the
    # separately published CLI wheel instead of the reviewed local binary.
    for name in (
        "pydantic",
        "pydantic-core",
        "annotated-types",
        "typing-extensions",
        "typing-inspection",
    ):
        distribution = importlib.metadata.distribution(name)
        versions[name] = distribution.version
        for relative in distribution.files:
            if (
                ".." in relative.parts
                or "__pycache__" in relative.parts
                or relative.suffix == ".pyc"
            ):
                continue
            origin = Path(distribution.locate_file(relative))
            if origin.is_file():
                target = dependencies / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
    package = BmadPackage.from_lock(Path(settings["bmad_source"]), Path(settings["uv"]))
    if package_digest(package.source) != package.source_sha256:
        raise ValueError("BMAD package differs from lock")
    lock = Path(__file__).resolve().parents[2] / "bmad-method.lock.json"
    shutil.copyfile(lock, archive / "bmad-method.lock.json")
    manifest["sdk_runtime"] = {
        "pin": asdict(pin),
        "sdk_source": str(copied),
        "sdk_dependencies": str(dependencies),
        "dependency_versions": versions,
        "budget": asdict(budget),
        "reasoning_effort": effort,
        "interaction_policy": interaction_policy,
        "project_recipe": project_recipe,
        "bmad_source": str(package.source),
        "bmad_source_sha256": package.source_sha256,
        "uv": str(package.uv),
        "service_key_env": settings["service_key_env"],
        "task_directories": {name: name for name in manifest["task_ids"]},
        "claim_source": "explicit spec_path only; discovered claims are retained without choosing one",
        "checkpoint_resume": "same process and aggregate budget only",
        "product_byte_limit": 32 * 1024 * 1024,
        "control_byte_limit": 16 * 1024 * 1024,
    }
    paths = [
        path
        for root in (copied, dependencies)
        for path in root.rglob("*")
        if path.is_file()
    ]
    if profile.get("model_catalog_json"):
        catalog = archive / "model-catalog.json"
        shutil.copyfile(
            Path(manifest["codex_home"]) / profile["model_catalog_json"], catalog
        )
        manifest["sdk_runtime"]["model_catalog"] = str(catalog)
        paths.append(catalog)
    paths += [archive / "bmad-method.lock.json", package.uv, package.node]
    # Include installed Node dependency files and stock sources in the freeze;
    # the model receives neither the package cache nor this host manifest.
    paths += [path for path in package.source.rglob("*") if path.is_file()]
    manifest["pins"].update({str(path): digest(path) for path in paths})
    manifest["hard_token_limit"] = budget.tokens
    manifest["token_limit_semantics"] = (
        "conservative serialized-input reservation and enforced output ceilings; not an exact provider-side token cap"
    )
    manifest["sdk_dependency_loading"] = (
        "frozen host-only sys.path; absent from candidate mounts"
    )
