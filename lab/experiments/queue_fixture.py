"""Versioned durable-queue fixture setup, independent of existing fixture fingerprints."""

import hashlib
import json
from pathlib import Path
import shutil
import sys

from setup_fixture import git, sha256

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/durable-queue-v1"
EVALUATOR_VERSION = "durable-queue-v2"


def evaluator_fingerprint():
    directory = Path(__file__).parent
    names = [
        "queue_fixture.py",
        "queue_cases.py",
        "queue_worker.py",
        "queue_cli_format.py",
        "queue_sandbox.py",
        "evaluate_queue.py",
        "evaluate_fixture.py",
        "evaluation_worker.py",
        "terminal_run.py",
        "setup_fixture.py",
        "fixture_registry.py",
        "structured_cases.py",
        "fixture_cases.py",
    ]
    files = {name: sha256(directory / name) for name in names}
    files["public_tests"] = sha256(FIXTURE / "project/tests/test_public.py")
    files["contract"] = sha256(FIXTURE / "project/CONTRACT.md")
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def setup(destination):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("queue fixture requires Python 3.12")
    destination = destination.resolve()
    destination.mkdir(exist_ok=False)
    repository = destination / "repository"
    shutil.copytree(
        FIXTURE / "project",
        repository,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(FIXTURE / "task.txt", repository / "TASK.md")
    (repository / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    files = {
        str(p.relative_to(repository)): sha256(p)
        for p in sorted(repository.rglob("*"))
        if p.is_file()
    }
    git(repository, "init", "--quiet", "--initial-branch=main", "--object-format=sha1")
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "durable-queue-v1 baseline")
    metadata = {
        "schema_version": 1,
        "fixture": "durable-queue-v1",
        "repository": str(repository),
        "commit": git(repository, "rev-parse", "HEAD"),
        "tree": git(repository, "rev-parse", "HEAD^{tree}"),
        "files": files,
        "task_sha256": sha256(FIXTURE / "task.txt"),
        "evaluator_sha256": evaluator_fingerprint(),
        "evaluator_version": EVALUATOR_VERSION,
        "python": {
            "path": str(Path(sys.executable).resolve()),
            "version": sys.version,
            "sha256": sha256(Path(sys.executable).resolve()),
        },
    }
    (destination / "fixture.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata
