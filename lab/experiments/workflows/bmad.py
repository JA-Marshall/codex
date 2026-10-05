"""Stock BMAD invocation and artifact claims; host grading remains independent."""

import hashlib
import json
from pathlib import Path
import re

from task_registry import relative_path
from workflows.bmad_install import inventory

STATUSES = {"draft", "ready-for-dev", "in-progress", "in-review", "blocked", "done"}


def spec_claim(installation, relative):
    path = relative_path(installation.workspace, relative)
    if not any(
        relative.startswith(name + "/")
        for name in installation.manifest["control_paths"]
    ):
        raise ValueError("spec must be in the declared control namespace")
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("missing or oversized spec")
    data = path.read_bytes()
    lines = data.decode("utf-8").splitlines()
    status = "unknown"
    if lines and lines[0] == "---" and "---" in lines[1:]:
        frontmatter = lines[1 : lines.index("---", 1)]
        fields = [line for line in frontmatter if re.match(r"^status\s*:", line)]
        if len(fields) == 1:
            match = re.fullmatch(
                r"status\s*:\s*(?:'([a-z-]+)'|\"([a-z-]+)\"|([a-z-]+))\s*(?:#.*)?",
                fields[0],
            )
            if match:
                value = next(value for value in match.groups() if value is not None)
                if value in STATUSES:
                    status = value
    return {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "status_claim": status,
    }


class BmadDispatch:
    """One stock invocation, with same-budget planning checkpoint continuation."""

    def __init__(self, run, installation, *, interactive=False):
        if Path(run.session.workspace) != installation.workspace:
            raise ValueError("BMAD installation and runtime workspace differ")
        self.run, self.installation, self.interactive = run, installation, interactive
        self.checkpoint = None
        self.started = False
        self.events = []

    def invoke(self, intent, *, halt_after_planning=False, spec=None):
        if self.started:
            raise ValueError("use resume for the existing invocation")
        self.started = True
        return self._turn(
            self.installation.kickoff(
                intent,
                interactive=self.interactive,
                halt_after_planning=halt_after_planning,
            ),
            spec,
            "invoke",
        )

    def resume(self):
        if not self.checkpoint or self.checkpoint["status_claim"] not in (
            "draft",
            "ready-for-dev",
            "in-progress",
            "in-review",
        ):
            raise ValueError(
                "no resumable checkpoint; blocked needs owner resolution and done requires a new follow-up run"
            )
        current = spec_claim(self.installation, self.checkpoint["path"])
        if current != self.checkpoint:
            raise ValueError("checkpoint changed outside this invocation")
        if self.run.result is not None:
            raise ValueError("cannot resume a closed run or reset its budget")
        prompt = self.installation.kickoff(
            "Continue the existing spec at "
            + str(self.installation.workspace / current["path"]),
            interactive=self.interactive,
        )
        return self._turn(prompt, current["path"], "resume")

    def _turn(self, prompt, spec, action):
        result = self.run.parent(prompt)
        self.installation.verify()
        self.checkpoint = (
            spec_claim(self.installation, spec) if spec is not None else None
        )
        claims = []
        if spec is None:
            for name in self.installation.manifest["control_paths"]:
                for relative in inventory(self.installation.workspace / name):
                    if relative.endswith(".md"):
                        claim = spec_claim(self.installation, name + "/" + relative)
                        if claim["status_claim"] != "unknown":
                            claims.append(claim)
        event = {
            "action": action,
            "transport": "codex-sdk-worker-bridge-v1",
            "entry": "bmad-build" if self.interactive else "bmad-build-auto",
            "turn": result,
            "spec_claim": self.checkpoint,
            "other_spec_claims": claims,
            "usage": self.run.ledger.snapshot(),
        }
        self.events.append(event)
        (self.run.artifacts / "bmad-dispatch.json").write_text(
            json.dumps(self.events, indent=2) + "\n"
        )
        return event
