"""Thin study CLI over the existing frozen campaign runner and reports."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from campaign_inputs import digest, load_campaign, read_json
from study_config import freeze_study, load_study
from study_ledger import append_record, register_variant, validate_variant
from study_resume import prepare_resume


def run_once(manifest_path):
    manifest_path = Path(manifest_path).resolve(strict=True)
    if read_json(manifest_path).get("study_stage") in ("validation", "confirmation"):
        raise ValueError(
            "held-out execution requires custodian preregistration and reservation"
        )
    manifest = load_campaign(manifest_path)
    attempts = manifest_path.parent / "study-attempts"
    attempts.mkdir(exist_ok=False)
    identity = uuid.uuid4().hex
    append_record(
        attempts,
        "started",
        dict(attempt_id=identity, manifest_sha256=digest(manifest_path)),
    )
    command = [
        manifest["python"],
        str(Path(manifest["archive"]) / "experiments/run_campaign.py"),
        "--execute",
        str(manifest_path),
        "--manifest-sha256",
        digest(manifest_path),
    ]
    try:
        completed = subprocess.run(command, check=False)
    except BaseException as error:
        append_record(
            attempts,
            "interrupted_or_launch_error",
            dict(
                attempt_id=identity,
                error=type(error).__name__,
                outcome="unknown; inspect campaign receipts",
            ),
        )
        raise
    result_path = manifest_path.parent / "results.json"
    append_record(
        attempts,
        "process_exited",
        dict(
            attempt_id=identity,
            exit_code=completed.returncode,
            results_sha256=digest(result_path) if result_path.is_file() else None,
        ),
    )
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("validate", "freeze"):
        command = sub.add_parser(name)
        command.add_argument("study", type=Path)
        if name == "freeze":
            command.add_argument("--registry", type=Path)
    command = sub.add_parser("run")
    command.add_argument("manifest", type=Path)
    command = sub.add_parser(
        "resume", help="Prepare only never-started slots in a fresh campaign"
    )
    command.add_argument("manifest", type=Path)
    command.add_argument("--output", type=Path, required=True)
    # Delegate established command parsers without reimplementing their semantics.
    for name in ("compare", "task", "workflow", "roadmap", "corpus"):
        command = sub.add_parser(name, add_help=False)
        command.add_argument("arguments", nargs=argparse.REMAINDER)
    if len(sys.argv) > 1 and sys.argv[1] in {
        "compare",
        "task",
        "workflow",
        "roadmap",
        "corpus",
    }:
        action, arguments = sys.argv[1], sys.argv[2:]
        if action == "workflow":
            if not arguments or arguments[0] != "propose":
                parser.error("workflow requires propose followed by revision arguments")
            arguments = arguments[1:]
        if action == "task":
            arguments = [*arguments, "--development-only"]
        filename = {
            "compare": "study_compare.py",
            "task": "task_library.py",
            "workflow": "workflow_proposal.py",
            "roadmap": "roadmap.py",
            "corpus": "corpus_manifest.py",
        }[action]
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name(filename)), *arguments],
            check=False,
        ).returncode
    args = parser.parse_args()
    if args.action == "validate":
        settings, data, pairs = load_study(args.study)
        print(
            json.dumps(
                dict(
                    valid=True,
                    stage=data["stage"],
                    trials=len(pairs) * settings.repetitions,
                    model_calls=0,
                    scope="configuration preflight; freeze additionally verifies runtime dependencies",
                )
            )
        )
    elif args.action == "freeze":
        if args.registry:
            _, data, _ = load_study(args.study)
            if not data.get("variant"):
                parser.error(
                    "--registry requires an explicit variant record in the study"
                )
            validate_variant(data["variant"], args.registry)
        manifest = freeze_study(args.study)
        path = Path(manifest["output"]) / "campaign.json"
        if args.registry:
            register_variant(args.registry, manifest["variant"], path)
        print(
            json.dumps(
                dict(
                    manifest=str(path),
                    sha256=digest(path),
                    trials=len(manifest["trials"]),
                    model_calls=0,
                )
            )
        )
    elif args.action == "run":
        return run_once(args.manifest)
    elif args.action == "resume":
        path = prepare_resume(args.manifest, args.output)
        print(
            json.dumps(
                dict(
                    manifest=str(path),
                    sha256=digest(path),
                    model_calls=0,
                    prepared_only=True,
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
