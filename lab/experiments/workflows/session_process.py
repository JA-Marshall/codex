"""Pinned Linux/WSL session boundary, including detached descendants.

PID namespaces are required: unsupported hosts fail before model execution.
This is a process boundary, not the private-grader filesystem sandbox.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sdk_hash():
    import openai_codex.client

    root = Path(openai_codex.client.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class RuntimePin:
    binary: str
    binary_sha256: str
    sdk_sha256: str
    source_commit: str
    python_sha256: str
    unshare_sha256: str
    launcher_sha256: str

    @classmethod
    def capture(cls, binary, source_commit):
        return cls(
            str(Path(binary).resolve()),
            file_hash(binary),
            sdk_hash(),
            source_commit,
            file_hash(sys.executable),
            file_hash("/usr/bin/unshare"),
            file_hash(Path(__file__).with_name("namespace_exec.py")),
        )

    def verify(self):
        if sys.platform != "linux":
            raise RuntimeError("SDK study sessions require Linux/WSL PID namespaces")
        if self != self.capture(self.binary, self.source_commit):
            raise ValueError("runtime or SDK differs from frozen pin")
        if len(self.source_commit) != 40 or any(
            c not in "0123456789abcdef" for c in self.source_commit
        ):
            raise ValueError("full source commit required")


class SessionProcess:
    def __init__(self, pin, home, marker, *, sandbox=None):
        pin.verify()
        self.marker = Path(marker)
        self.pin = pin
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=False)
        self.identity = None
        self.sandbox = sandbox

    def launch_args(self, *, command=None, legacy_provider_key=None):
        command = command or [self.pin.binary, "app-server", "--listen", "stdio://"]
        if command[0] != self.pin.binary:
            raise ValueError("namespace command must use the pinned binary")
        if self.sandbox is not None:
            command = self.sandbox.wrap(self.pin.binary, self.home, command)
        tool_dirs = (
            [str(path.parent) for path in self.sandbox.tools] if self.sandbox else []
        )
        path = ":".join([*tool_dirs, "/usr/local/bin", "/usr/bin", "/bin"])
        # env -i prevents inheriting provider credentials and user configuration.
        return (
            "/usr/bin/env",
            "-i",
            f"PATH={path}",
            f"HOME={self.home}",
            f"CODEX_HOME={self.home}",
            f"UV_PYTHON={Path(sys.executable).resolve()}",
            "UV_PYTHON_DOWNLOADS=never",
            *(
                [
                    f"TMPDIR={'/tmp' if legacy_provider_key is not None else self.home / 'agent-tmp'}"
                ]
                if self.sandbox
                else []
            ),
            "CODEX_APP_SERVER_DISABLE_MANAGED_CONFIG=1",
            "RUST_LOG=error",
            *(
                [f"LAB_LEGACY_PROVIDER_KEY={legacy_provider_key}"]
                if legacy_provider_key is not None
                else []
            ),
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--mount",
            "--pid",
            "--fork",
            "--kill-child=SIGKILL",
            str(Path(sys.executable).resolve()),
            str(Path(__file__).with_name("namespace_exec.py")),
            str(self.marker),
            os.readlink("/proc/self/ns/mnt"),
            *command,
        )

    def launched(self):
        self.identity = json.loads(self.marker.read_text())
        if (
            os.readlink(f"/proc/{self.identity['pid']}/ns/pid")
            != self.identity["namespace"]
        ):
            raise RuntimeError("namespace identity mismatch")

    def stopped(self, timeout=5):
        if self.identity is None and self.marker.exists():
            self.identity = json.loads(self.marker.read_text())
        if self.identity is None:
            return False
        deadline = time.monotonic() + timeout
        while True:
            try:
                fields = (
                    Path(f"/proc/{self.identity['pid']}/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()
                )
                # Linux tears down all namespace members (including nested PID
                # namespaces) before its init finishes exiting. Start ticks
                # prevent confusing a recycled outer PID with this session.
                if fields[19] != self.identity["start_ticks"] or fields[0] in (
                    "Z",
                    "X",
                ):
                    return True
            except FileNotFoundError:
                return True
            except PermissionError:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    def evidence(self):
        return {
            "runtime": asdict(self.pin),
            "namespace": self.identity,
            "launcher_sha256": file_hash(Path(__file__).with_name("namespace_exec.py")),
            **(self.sandbox.evidence(self.home) if self.sandbox else {}),
        }
