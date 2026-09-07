"""Run repository-task commands inside the existing restricted Linux sandbox."""

import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import time

MAX_OUTPUT = 1024 * 1024


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def observe(sandbox, repository, scratch, command, *, cwd=None, stdin="", toolchain=None, write_root=None):
    sandbox, repository, scratch = Path(sandbox).absolute(), Path(repository), Path(scratch)
    write_root = Path(write_root) if write_root else scratch
    if sys.platform != "linux" or sandbox.name != "codex-linux-sandbox":
        raise ValueError("repository tasks require the Linux sandbox alias")
    reads = [Path(sys.base_prefix), sandbox, sandbox.resolve(),
             sandbox.resolve().parent / "codex-resources", repository]
    if toolchain is not None:
        reads.append(Path(toolchain))
    entries = [{"path": {"type": "path", "path": str(path)}, "access": "read"}
               for path in reads if path.exists()]
    entries.extend([
        {"path": {"type": "special", "value": {"kind": "minimal"}}, "access": "read"},
        {"path": {"type": "path", "path": str(scratch)}, "access": "read"},
        {"path": {"type": "path", "path": str(write_root)}, "access": "write"},
    ])
    profile = {"type": "managed", "network": "restricted",
               "file_system": {"type": "restricted", "entries": entries}}
    invocation = [str(sandbox), "--sandbox-policy-cwd", str(repository),
                  "--permission-profile", json.dumps(profile), "--", *command]
    environment = {
        "PATH": (str(Path(toolchain) / "bin") + ":" if toolchain else "") + "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8", "HOME": str(write_root), "TMPDIR": str(write_root),
        "PYTHONDONTWRITEBYTECODE": "1", "CARGO_HOME": str(scratch / "cargo-home"),
        "CARGO_TARGET_DIR": str(scratch / "target"), "CARGO_BUILD_JOBS": "1",
    }
    if toolchain:
        environment["RUSTC"] = str(Path(toolchain) / "bin/rustc")
        environment["RUSTDOC"] = str(Path(toolchain) / "bin/rustdoc")
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(invocation, cwd=cwd or repository, env=environment,
                                   stdin=subprocess.PIPE, stdout=out, stderr=err,
                                   start_new_session=True, preexec_fn=limits)
        timed_out = False
        try:
            process.communicate(stdin.encode(), timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # The entire isolated process group belongs to this observation.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(MAX_OUTPUT + 1), err.read(MAX_OUTPUT + 1)
    invalid_utf8 = False
    try:
        stdout.decode("utf-8")
        stderr.decode("utf-8")
    except UnicodeDecodeError:
        invalid_utf8 = True
    return {
        "exit_code": process.returncode, "timeout": timed_out,
        "output_truncated": len(stdout) > MAX_OUTPUT or len(stderr) > MAX_OUTPUT,
        "invalid_utf8": invalid_utf8,
        "stdout": stdout[:MAX_OUTPUT].decode(errors="replace"),
        "stderr": stderr[:MAX_OUTPUT].decode(errors="replace"),
        "wall_clock_ms": round((time.monotonic() - started) * 1000),
    }
