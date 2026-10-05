"""Host-run public checks on a stable copy; no private rubric is read."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time

from evaluate_task import render
from task_sandbox import observe
from workflows.bmad_install import inventory


class PublicVerifier:
    def __init__(self, task, sandbox, toolchain=None):
        self.tests = task.root / "project/tests"
        self.test_identity = inventory(self.tests)
        self.commands = [
            command
            for command in (task.manifest["build"], task.manifest["public_command"])
            if command
        ]
        self.sandbox, self.toolchain = sandbox, toolchain

    def __call__(self, run):
        workspace = Path(run.session.workspace)
        before = inventory(workspace, exclude=(".git",), max_total=32 * 1024 * 1024)
        if inventory(self.tests) != self.test_identity:
            raise ValueError("frozen public tests changed")
        observations = []
        with tempfile.TemporaryDirectory(prefix="workflow-public-") as temporary:
            base = Path(temporary)
            candidate = base / "candidate"
            candidate.mkdir()
            for name, metadata in before.items():
                content = (workspace / name).read_bytes()
                if (
                    len(content) != metadata["size"]
                    or hashlib.sha256(content).hexdigest() != metadata["sha256"]
                ):
                    raise ValueError("product changed while copying public-check input")
                destination = candidate / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            if (
                inventory(workspace, exclude=(".git",), max_total=32 * 1024 * 1024)
                != before
            ):
                raise ValueError("product changed while copying public-check input")
            tests = candidate / "tests"
            if tests.exists() and not tests.is_dir():
                tests.unlink()
            tests.mkdir(exist_ok=True)
            # Preserve added regression tests and restore original public tests.
            for name in self.test_identity:
                destination = tests / name
                if destination.is_dir():
                    shutil.rmtree(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((self.tests / name).read_bytes())
            frozen = inventory(candidate)
            for index, command in enumerate(self.commands):
                remaining = run.ledger.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "project deadline expired before public verification"
                    )
                scratch = base / ("scratch-" + str(index))
                scratch.mkdir()
                result = observe(
                    self.sandbox,
                    candidate,
                    scratch,
                    render(command, candidate, scratch, self.toolchain),
                    toolchain=self.toolchain,
                    timeout=min(120, remaining),
                )
                observations.append(
                    {
                        **result,
                        "stdout": result["stdout"][:4096],
                        "stderr": result["stderr"][:4096],
                        "feedback_truncated": len(result["stdout"]) > 4096
                        or len(result["stderr"]) > 4096,
                    }
                )
                if inventory(candidate) != frozen:
                    raise ValueError("public verification modified its read-only input")
            if inventory(self.tests) != self.test_identity:
                raise ValueError("frozen public tests changed during verification")
        return {
            "captured_product_sha256": hashlib.sha256(
                json.dumps(before, sort_keys=True).encode()
            ).hexdigest(),
            "check_input_sha256": hashlib.sha256(
                json.dumps(frozen, sort_keys=True).encode()
            ).hexdigest(),
            "checks": observations,
            "passed": bool(observations)
            and all(
                result["exit_code"] == 0
                and not result["timeout"]
                and not result["output_truncated"]
                and not result["invalid_utf8"]
                for result in observations
            ),
            "visibility": "public checks only; independent private grading occurs after final shutdown",
        }
