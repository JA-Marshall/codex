"""Install the pinned stock BMAD package; preserve its renderer and prompts."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from workflows.filesystem import SessionSandbox

BMAD_VERSION = "6.12.0"
BMAD_COMMIT = "05bfbd46d00766ec88eb9b42e76be2c575d64d7b"
PACKAGE_PATHS = (
    "src",
    "tools",
    "package.json",
    "package-lock.json",
    "bmad-modules.yaml",
    "LICENSE",
)


def inventory(root, *, exclude=(), max_total=16 * 1024 * 1024):
    root = Path(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("asset root must be an actual directory")
    result = {}
    total = count = 0
    pending = [Path(root)]
    while pending:
        for path in pending.pop().iterdir():
            count += 1
            if count > 4096:
                raise ValueError("asset entry quota exceeded")
            relative = path.relative_to(root).as_posix()
            if any(
                relative == prefix or relative.startswith(prefix + "/")
                for prefix in exclude
            ):
                continue
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError(
                    f"asset link or special file is not permitted: {relative}"
                )
            total += metadata.st_size
            if metadata.st_size > 2 * 1024 * 1024 or total > max_total:
                raise ValueError("asset byte quota exceeded")
            result[relative] = {
                "size": metadata.st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    return result


def package_digest(source):
    files = {}
    for name in PACKAGE_PATHS:
        path = source / name
        if path.is_dir():
            files.update(
                {name + "/" + key: value for key, value in inventory(path).items()}
            )
        else:
            files[name] = {
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class BmadPackage:
    source: Path
    source_sha256: str
    uv: Path
    node: Path = Path("/usr/bin/node")

    @classmethod
    def from_lock(cls, source, uv):
        lock = json.loads(
            (Path(__file__).parents[2] / "bmad-method.lock.json").read_text()
        )
        if lock["version"] != BMAD_VERSION or lock["commit"] != BMAD_COMMIT:
            raise ValueError("unsupported BMAD lock")
        return cls(Path(source), lock["source_sha256"], Path(uv))

    def install(self, workspace, evidence):
        workspace, evidence = Path(workspace).resolve(), Path(evidence).resolve()
        if (
            json.loads((self.source / "package.json").read_text())["version"]
            != BMAD_VERSION
            or package_digest(self.source) != self.source_sha256
        ):
            raise ValueError("BMAD source differs from the reviewed pin")
        if any(
            (workspace / name).exists() for name in ("_bmad", "_bmad-output", ".agents")
        ):
            raise ValueError(
                "BMAD control namespace already exists; do not overwrite it"
            )
        evidence.mkdir(parents=True, exist_ok=False)
        command = [
            str(self.node),
            str(self.source / "tools/installer/bmad-cli.js"),
            "install",
            "--directory",
            str(workspace),
            "--modules",
            "bmm",
            "--tools",
            "codex",
            "--user-name",
            "Developer",
            "--communication-language",
            "English",
            "--document-output-language",
            "English",
            "--output-folder",
            "_bmad-output",
            "--no-shims",
            "--yes",
        ]
        provision_home = evidence / "installer-home"
        provision_home.mkdir()
        env = {
            "PATH": str(self.uv.parent) + os.pathsep + "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(provision_home),
            "LANG": "C.UTF-8",
            "NO_COLOR": "1",
            "UV_PYTHON": str(Path(sys.executable).resolve()),
            "UV_PYTHON_DOWNLOADS": "never",
        }
        completed = subprocess.run(
            command,
            cwd=self.source,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        (evidence / "install.log").write_bytes(completed.stdout[: 1024 * 1024])
        if completed.returncode or len(completed.stdout) > 1024 * 1024:
            raise RuntimeError("stock BMAD installer failed or exceeded its log limit")
        shutil.copyfile(self.source / "LICENSE", workspace / "_bmad/LICENSE")
        output = workspace / "_bmad-output"
        output.mkdir(exist_ok=True)
        # Only reserved workflow namespaces are excluded from stock local commits.
        # Product scope is independently scanned without consulting Git ignores.
        git_info = workspace / ".git/info"
        if (workspace / ".git").is_dir() and not (workspace / ".git").is_symlink():
            git_info.mkdir(exist_ok=True)
            with (git_info / "exclude").open("a") as stream:
                stream.write("\n/_bmad/\n/_bmad-output/\n/.agents/\n")
        rendered = {}
        for skill in ("bmad-build-auto", "bmad-build"):
            skill_root = workspace / ".agents/skills" / skill
            render = [
                str(self.uv),
                "run",
                "--no-cache",
                str(workspace / "_bmad/scripts/render_skill.py"),
                "--project-root",
                str(workspace),
                "--skill",
                str(skill_root),
            ]
            result = subprocess.run(
                render,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            lines = result.stdout.strip().splitlines()
            if (
                result.returncode
                or len(lines) != 1
                or not lines[0].startswith("read and follow ")
            ):
                raise RuntimeError("stock BMAD renderer failed")
            entry = Path(lines[0][len("read and follow ") :])
            if (
                not entry.resolve().is_relative_to(
                    (workspace / "_bmad/render").resolve()
                )
                or not entry.is_file()
            ):
                raise ValueError("renderer output escaped the declared namespace")
            rendered[skill] = str(entry)
        protected = {
            "_bmad": inventory(workspace / "_bmad"),
            ".agents": inventory(workspace / ".agents"),
        }
        manifest = {
            "schema_version": 1,
            "version": BMAD_VERSION,
            "source_commit": BMAD_COMMIT,
            "source_sha256": self.source_sha256,
            "installer": command,
            "rendered": rendered,
            "protected": protected,
            "control_paths": ["_bmad-output"],
            "uv_sha256": hashlib.sha256(self.uv.read_bytes()).hexdigest(),
            "node_sha256": hashlib.sha256(self.node.read_bytes()).hexdigest(),
        }
        (evidence / "installation.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        return BmadInstallation(workspace, manifest, self.uv)


@dataclass(frozen=True)
class BmadInstallation:
    workspace: Path
    manifest: dict
    uv: Path

    def sandbox(self):
        return SessionSandbox(
            self.workspace,
            protected=(self.workspace / "_bmad", self.workspace / ".agents"),
            controls=(self.workspace / "_bmad-output",),
            tools=(self.uv,),
        )

    def verify(self):
        for name, expected in self.manifest["protected"].items():
            if inventory(self.workspace / name) != expected:
                raise ValueError(f"protected BMAD assets changed: {name}")

    def kickoff(self, intent, *, interactive=False, halt_after_planning=False):
        skill = "bmad-build" if interactive else "bmad-build-auto"
        if not isinstance(intent, str) or len(intent.encode()) > 128 * 1024:
            raise ValueError("invalid bounded invocation")
        self.verify()
        return (
            f"Invoke the installed {skill} skill at {self.workspace / '.agents/skills' / skill / 'SKILL.md'}. "
            "Follow its stock renderer and workflow. For subagents use run_workers with the exact supplied prompts, "
            "writable=true for the implementation worker and false for reviewers. Submit every review layer in one group. "
            "Use continue_worker to re-engage the same implementation worker. This is a Codex transport port; "
            "do not change the installed review policy or preload reviewer instruction files. "
            + ("Halt after planning. " if halt_after_planning else "")
            + "\n\nInvocation:\n"
            + intent
        )
