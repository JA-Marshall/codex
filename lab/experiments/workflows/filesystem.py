"""Filesystem capability boundary for scored SDK trials, outside all model tools."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys


@dataclass(frozen=True)
class SessionSandbox:
    workspace: Path
    protected: tuple[Path, ...] = ()
    controls: tuple[Path, ...] = ()
    tools: tuple[Path, ...] = ()

    def _paths(self, home, binary):
        workspace = self.workspace.resolve(strict=True)
        read = {Path(sys.base_prefix).resolve(), Path(binary).resolve()}
        resources = Path(binary).resolve().parent / "codex-resources"
        if resources.exists():
            read.add(resources)
        read.update(path.resolve(strict=True) for path in self.protected)
        for tool in self.tools:
            read.update((tool.absolute(), tool.resolve(strict=True)))
        writes = {workspace, home, workspace / ".git"}
        writes.update(path.resolve(strict=True) for path in self.controls)
        read.update(path for path in self._git_protected() if path.exists())
        if any(str(path) in ("/", "/home", "/tmp", "/mnt") for path in read | writes):
            raise ValueError("trial capabilities must name specific resources")
        return read, writes

    def _git_protected(self):
        return tuple(
            self.workspace.resolve() / ".git" / name
            for name in ("config", "hooks", "info", "objects/info")
        )

    def wrap(self, binary, home, command):
        read, writes = self._paths(home, binary)
        entries = [
            {
                "path": {"type": "special", "value": {"kind": "minimal"}},
                "access": "read",
            }
        ]
        for access, paths in (("write", writes), ("read", read)):
            entries.extend(
                {"path": {"type": "path", "path": str(path)}, "access": access}
                for path in sorted(paths)
                if path.exists()
            )
        profile = {
            "type": "managed",
            "network": "enabled",
            "file_system": {"type": "restricted", "entries": entries},
        }
        self._write_profiles(home, read)
        bwrap = Path(binary).resolve().parent / "codex-resources/bwrap"
        if not bwrap.is_file():
            raise ValueError("pinned runtime's bundled bubblewrap is required")
        # Apply a mount boundary around app-server, not a command seccomp policy:
        # app-server must itself be able to create its nested command sandboxes.
        args = [
            str(bwrap),
            "--unshare-user",
            "--unshare-pid",
            "--as-pid-1",
            "--die-with-parent",
            "--new-session",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CAP_SETFCAP",
            "--tmpfs",
            "/",
            # Nested bubblewrap needs /tmp to stage its root. Production
            # /home workspaces do not create it incidentally via other mounts.
            "--tmpfs",
            "/tmp",
        ]
        for path in ("/usr", "/etc", "/bin", "/sbin", "/lib", "/lib64"):
            if Path(path).exists():
                args.extend(["--ro-bind", path, path])
        # Broad grants precede their narrow, immutable overlays.
        mounts = {path: "--bind" for path in writes if path.exists()}
        mounts.update({path: "--ro-bind" for path in read})
        for path, mode in sorted(
            mounts.items(), key=lambda item: (len(item[0].parts), str(item[0]))
        ):
            args.extend([mode, str(path), str(path)])
        args.extend(
            [
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--chdir",
                str(self.workspace),
                "--",
                *command,
            ]
        )
        resources = {}
        for resource in sorted(bwrap.parent.rglob("*")):
            if resource.is_file():
                resources[resource.relative_to(bwrap.parent).as_posix()] = (
                    hashlib.sha256(resource.read_bytes()).hexdigest()
                )
        record = {
            "requested_profile": profile,
            "argv": args,
            "runtime_resources_sha256": resources,
        }
        (home / "outer-sandbox.json").write_text(json.dumps(record, indent=2) + "\n")
        return args

    def _write_profiles(self, home, reads):
        cache = home / ".cache"
        cache.mkdir()
        scratch = home / "agent-tmp"
        scratch.mkdir()
        common = {":minimal": "read", str(cache): "write", str(scratch): "write"}
        common.update({str(path): "read" for path in reads})
        profiles = {}
        for name, access, control_access in (
            ("study_writer", "write", "write"),
            ("study_reviewer", "read", "read"),
            ("study_planner", "read", "write"),
        ):
            entries = {**common, str(self.workspace.resolve()): access}
            entries[str(self.workspace.resolve() / ".git")] = access
            entries.update({str(path.resolve()): "read" for path in self.protected})
            entries.update(
                {str(path): "read" for path in self._git_protected() if path.exists()}
            )
            entries.update(
                {str(path.resolve()): control_access for path in self.controls}
            )
            profiles[name] = {"filesystem": entries, "network": {"enabled": False}}
        (home / "thread-permissions.json").write_text(
            json.dumps(profiles, indent=2) + "\n"
        )

    def thread_permissions(self, home, writable, *, role=None):
        return {
            "permissions": "study_planner"
            if role == "planner"
            else "study_writer"
            if writable
            else "study_reviewer",
            "config": {
                "permissions": json.loads(
                    (home / "thread-permissions.json").read_text()
                )
            },
        }

    def evidence(self, home):
        data = (home / "outer-sandbox.json").read_bytes()
        return {
            "outer_filesystem_sha256": hashlib.sha256(data).hexdigest(),
            "outer_filesystem": json.loads(data),
        }
