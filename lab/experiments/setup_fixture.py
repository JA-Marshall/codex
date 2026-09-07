"""Create a deterministic, isolated task checkout. Never copy hidden evaluation inputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "csv-summary-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluator_fingerprint() -> str:
    scripts = Path(__file__).resolve().parent
    files = [
        scripts / name
        for name in [
            "evaluate_fixture.py",
            "evaluation_worker.py",
            "fixture_cases.py",
            "setup_fixture.py",
        ]
    ] + [FIXTURE / "project/tests/test_public.py"]
    content = {
        str(path.relative_to(FIXTURE.parents[1])): sha256(path) for path in files
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def git(repository: Path, *arguments: str) -> str:
    environment = {
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Codex Lab",
        "GIT_AUTHOR_EMAIL": "lab@example.invalid",
        "GIT_COMMITTER_NAME": "Codex Lab",
        "GIT_COMMITTER_EMAIL": "lab@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    }
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            *arguments,
        ],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    return result.stdout.strip()


def setup(destination: Path) -> dict:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("fixture setup requires Python 3.12")
    destination = destination.resolve()
    destination.mkdir(parents=False, exist_ok=False)
    repository = destination / "repository"
    shutil.copytree(
        FIXTURE / "project",
        repository,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(FIXTURE / "task.txt", repository / "TASK.md")
    (repository / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    files = {
        str(path.relative_to(repository)): sha256(path)
        for path in sorted(repository.rglob("*"))
        if path.is_file()
    }
    git(repository, "init", "--quiet", "--initial-branch=main", "--object-format=sha1")
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "csv-summary-v1 baseline")
    metadata = {
        "schema_version": 1,
        "fixture": "csv-summary-v1",
        "repository": str(repository),
        "commit": git(repository, "rev-parse", "HEAD"),
        "tree": git(repository, "rev-parse", "HEAD^{tree}"),
        "files": files,
        "task_sha256": sha256(FIXTURE / "task.txt"),
        "evaluator_sha256": evaluator_fingerprint(),
        "python": {
            "path": str(Path(sys.executable).resolve()),
            "version": sys.version,
            "sha256": sha256(Path(sys.executable).resolve()),
        },
    }
    (destination / "fixture.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(setup(args.destination), indent=2))
