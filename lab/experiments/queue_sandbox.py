"""Small stateful observation adapter; retain the upstream sandbox and old evaluator."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from evaluate_fixture import MAX_OUTPUT, limits

WORKER = Path(__file__).with_name("queue_worker.py")


def observe(sandbox, repository, scratch, mode, request):
    reads = [
        Path(sys.base_prefix),
        sandbox,
        sandbox.resolve(),
        sandbox.resolve().parent / "codex-resources",
        WORKER,
        WORKER.with_name("queue_cli_format.py"),
        repository,
    ]
    entries = [
        {"path": {"type": "path", "path": str(p)}, "access": "read"}
        for p in reads
        if p.exists()
    ]
    entries += [
        {"path": {"type": "special", "value": {"kind": "minimal"}}, "access": "read"},
        {"path": {"type": "path", "path": str(scratch)}, "access": "write"},
    ]
    profile = {
        "type": "managed",
        "network": "restricted",
        "file_system": {"type": "restricted", "entries": entries},
    }
    command = [
        str(sandbox),
        "--sandbox-policy-cwd",
        str(repository),
        "--permission-profile",
        json.dumps(profile),
        "--",
        str(Path(sys.executable).resolve()),
        "-I",
        "-B",
        str(WORKER),
        str(repository),
        str(scratch),
        mode,
    ]
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
    }
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            result = subprocess.run(
                command,
                executable=str(sandbox),
                input=json.dumps(request).encode(),
                cwd=repository,
                env=environment,
                stdout=out,
                stderr=err,
                timeout=20,
                preexec_fn=limits,
            )
            code, timeout = result.returncode, False
        except subprocess.TimeoutExpired:
            code, timeout = None, True
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(MAX_OUTPUT + 1), err.read(MAX_OUTPUT + 1)
    try:
        value = json.loads(stdout) if code == 0 and len(stdout) <= MAX_OUTPUT else None
    except (ValueError, UnicodeError):
        value = None
    return {
        "value": value,
        "exit_code": code,
        "timeout": timeout,
        "stdout": stdout.decode(errors="replace"),
        "stderr": stderr.decode(errors="replace"),
        "wall_clock_ms": round((time.monotonic() - started) * 1000),
    }
