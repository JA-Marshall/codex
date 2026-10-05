"""Development authoring certificates backed by complete calibration evidence."""

import json
from pathlib import Path

from campaign_inputs import digest
from corpus_manifest import fingerprint, valid_hash, valid_id
from task_registry import evaluator_fingerprint, inventory, load_task, read_json


def driver_fingerprint():
    return {
        name: digest(Path(__file__).with_name(name))
        for name in (
            "task_library.py",
            "calibration_changes.py",
            "corpus_calibration.py",
        )
    }


def checked_json(path):
    path = Path(path)
    if (
        path.absolute() != path.resolve(strict=True)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 2 * 1024 * 1024
    ):
        raise ValueError(
            "certificate evidence path must be a regular file without aliases"
        )
    return read_json(path)


def certify_development(task_root, authoring_path, calibration_path, output):
    task_root = Path(task_root)
    if task_root.absolute() != task_root.resolve(strict=True):
        raise ValueError("task root must not contain aliases")
    # Read only task metadata until the development classification is known.
    if checked_json(task_root / "manifest.json").get("split") != "development":
        raise ValueError(
            "held-out authoring/calibration requires the separate custodian"
        )
    task = load_task(task_root)
    if task.manifest["schema_version"] != 2:
        raise ValueError("new corpus certificates require TaskSpec v2")
    authoring = checked_json(authoring_path)
    fields = {
        "schema_version",
        "task_id",
        "project_id",
        "lineage_id",
        "duplicate_family",
        "mutant_roles",
    }
    if (
        not isinstance(authoring, dict)
        or set(authoring) != fields
        or authoring["schema_version"] != 1
        or authoring["task_id"] != task.name
        or authoring["project_id"] != task.manifest["project_id"]
        or any(
            not valid_id(authoring[key]) for key in ("lineage_id", "duplicate_family")
        )
    ):
        raise ValueError("invalid authoring identity and ancestry")
    roles = authoring["mutant_roles"]
    mutants = set(task.manifest["mutants"])
    if (
        not isinstance(roles, dict)
        or set(roles) != mutants
        or any(
            role not in ("wrong-interpretation", "visible-test-only", "regression")
            for role in roles.values()
        )
        or not {"wrong-interpretation", "visible-test-only"} <= set(roles.values())
    ):
        raise ValueError("declare wrong-interpretation and visible-test-only mutants")
    source_hash = fingerprint(inventory(task_root))
    calibration_path = Path(calibration_path)
    report = checked_json(calibration_path)
    if (
        report.get("schema_version") != 1
        or report.get("model_calls") != 0
        or report.get("calibrated") is not True
        or report.get("task_inputs", {}).get(task.name) != source_hash
        or report.get("evaluator_sha256") != evaluator_fingerprint()
        or report.get("calibration_driver_sha256") != driver_fingerprint()
    ):
        raise ValueError("calibration must bind current task assets and evaluator")
    rows = report.get("records")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        raise ValueError("bounded complete calibration records required")
    selected = [row for row in rows if row.get("task") == task.name]
    positives = {"solution", *task.manifest.get("valid_alternatives", [])}
    variants = {"baseline", "irrelevant-patch", *positives, *mutants}
    if (
        len(selected) != len(variants)
        or {row.get("variant") for row in selected} != variants
    ):
        raise ValueError(
            "calibration must include baseline, irrelevant, reference and every mutant/alternative"
        )
    policy = checked_json(task_root / "private/policy.json")
    evaluations = {}
    for row in selected:
        variant = row["variant"]
        evaluation_path = Path(row["evaluation"])
        if not evaluation_path.resolve(strict=True).is_relative_to(
            calibration_path.parent.resolve(strict=True)
        ):
            raise ValueError("evaluation escapes calibration evidence directory")
        evaluation = checked_json(evaluation_path)
        expected = variant in positives
        if (
            digest(evaluation_path) != row.get("evaluation_sha256")
            or evaluation.get("fixture") != task.name
            or evaluation.get("schema_version") != 1
            or evaluation.get("task_success") is not expected
            or row.get("expected_pass") is not expected
            or row.get("actual_pass") is not expected
            or row.get("calibrated") is not True
        ):
            raise ValueError("calibration row disagrees with hash-bound evaluation")
        if variant in mutants:
            failures = policy.get("mutant_failures", {}).get(variant, [])
            if not failures or any(
                evaluation.get("requirement_coverage", {}).get(name) is not False
                for name in failures
            ):
                raise ValueError("mutant must fail its declared critical requirements")
            if (
                roles[variant] == "visible-test-only"
                and evaluation.get("public_test_success") is not True
            ):
                raise ValueError(
                    "visible-test-only mutant must actually pass public tests"
                )
        evaluations[variant] = digest(evaluation_path)
    if source_hash != fingerprint(inventory(task_root)):
        raise ValueError("task assets changed while certifying")
    certificate = dict(
        schema_version=1,
        task_id=task.name,
        project_id=task.manifest["project_id"],
        lineage_id=authoring["lineage_id"],
        duplicate_family=authoring["duplicate_family"],
        content_sha256=source_hash,
        authoring_sha256=digest(authoring_path),
        calibration_report_sha256=digest(calibration_path),
        evaluator_sha256=evaluator_fingerprint(),
        calibration_driver_sha256=driver_fingerprint(),
        evaluation_sha256=evaluations,
        calibrated=True,
        model_calls=0,
        limitation="Executable calibration and declared mutant roles; semantic realism and independence still require review.",
    )
    output = Path(output)
    if (
        output.resolve().is_relative_to(task_root.resolve())
        or output.absolute() != output.resolve()
    ):
        raise ValueError(
            "certificate output must be outside task assets without aliases"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(certificate, stream, indent=2)
        stream.write("\n")
    return output


def verify_certificate(path, entry, task=None):
    value = checked_json(path)
    fields = {
        "schema_version",
        "task_id",
        "project_id",
        "lineage_id",
        "duplicate_family",
        "content_sha256",
        "authoring_sha256",
        "calibration_report_sha256",
        "evaluator_sha256",
        "calibration_driver_sha256",
        "evaluation_sha256",
        "calibrated",
        "model_calls",
        "limitation",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["schema_version"] != 1
        or type(value["model_calls"]) is not int
        or any(
            not valid_hash(value[key])
            for key in (
                "content_sha256",
                "authoring_sha256",
                "calibration_report_sha256",
            )
        )
    ):
        raise ValueError("incomplete development calibration certificate")
    evaluations = value["evaluation_sha256"]
    if (
        not isinstance(evaluations, dict)
        or not 5 <= len(evaluations) <= 20
        or not {"baseline", "irrelevant-patch", "solution"} <= set(evaluations)
        or any(
            not valid_id(key) or not valid_hash(sha) for key, sha in evaluations.items()
        )
    ):
        raise ValueError("certificate requires complete variant evidence fingerprints")
    if task is not None and set(evaluations) != {
        "baseline",
        "irrelevant-patch",
        "solution",
        *task.manifest["mutants"],
        *task.manifest.get("valid_alternatives", []),
    }:
        raise ValueError("certificate variant inventory differs from selected task")
    if (
        digest(path) != entry["calibration_sha256"]
        or value.get("calibrated") is not True
        or value.get("model_calls") != 0
        or value.get("evaluator_sha256") != evaluator_fingerprint()
        or value.get("calibration_driver_sha256") != driver_fingerprint()
        or any(
            value.get(key) != entry[key]
            for key in (
                "project_id",
                "lineage_id",
                "duplicate_family",
                "content_sha256",
            )
        )
        or value.get("task_id") != entry["id"]
    ):
        raise ValueError(
            "development certificate differs from index or current evaluator"
        )
