"""Added recipe: stock headless spec, caller-authored stories, stock BuildAuto."""

import json
from pathlib import Path
import re
import uuid

from task_registry import IDENTIFIER, relative_path
from workflows.bmad import BmadDispatch, spec_claim

IDENTITY = "bmad-orchestrated-v6.12.0-recipe1"


def parse_plan(text):
    if len(text.encode()) > 32768:
        raise ValueError("increment plan exceeds limit")
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"increments"}:
        raise ValueError("expected an ordered increment plan")
    increments = value["increments"]
    if not isinstance(increments, list) or not 1 <= len(increments) <= 4:
        raise ValueError("one to four known-scope increments required")
    seen = set()
    for item in increments:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "intent",
            "acceptance",
            "depends_on",
        }:
            raise ValueError("invalid increment fields")
        identity, intent, checks, dependencies = (
            item[key] for key in ("id", "intent", "acceptance", "depends_on")
        )
        if (
            not isinstance(identity, str)
            or not re.fullmatch("[a-z][a-z0-9-]{0,79}", identity)
            or identity in seen
            or any(
                identity.startswith(old + "-") or old.startswith(identity + "-")
                for old in seen
            )
            or not isinstance(intent, str)
            or not 1 <= len(intent.encode()) <= 4096
            or not isinstance(checks, list)
            or not 1 <= len(checks) <= 8
            or any(
                not isinstance(check, str) or not 1 <= len(check.encode()) <= 512
                for check in checks
            )
            or not isinstance(dependencies, list)
            or any(not isinstance(dep, str) or dep not in seen for dep in dependencies)
            or len(set(dependencies)) != len(dependencies)
        ):
            raise ValueError("invalid bounded increment or non-prior dependency")
        seen.add(identity)
    return increments


class BmadOrchestrated:
    def __init__(self, run, installation):
        if Path(run.session.workspace) != installation.workspace:
            raise ValueError("orchestration workspace mismatch")
        self.run, self.installation = run, installation

    def invoke(self, intent, slug):
        if not IDENTIFIER.fullmatch(slug):
            raise ValueError("explicit bounded spec slug required")
        install, run = self.installation, self.run
        record = {
            "recipe": IDENTITY,
            "increments": [],
            "turn": None,
            "recipe_status": "failed",
        }
        target = run.artifacts / "orchestrated-result.json"
        try:
            install.verify()
            spec_worker = "spec-" + uuid.uuid4().hex
            run.session.new_thread(spec_worker, role="planner")
            spec_turn = run.session.turn(
                spec_worker,
                f"Invoke stock bmad-spec at {install.workspace / '.agents/skills/bmad-spec/SKILL.md'} in headless mode. "
                f"The caller supplies slug={slug}. Derive or update through the stock memlog procedure, preserving capability IDs. "
                "Return only its headless JSON status/files response. Do not perform interactive Story Breakdown or implement product code. "
                "Ask the authorized owner for missing product facts when necessary.\n\nIntent:\n"
                + intent,
            )
            record.update(spec_turn=spec_turn, turn=spec_turn)
            if spec_turn["status"] != "completed":
                return record
            if len(spec_turn["text"].encode()) > 16384:
                raise ValueError("headless spec response exceeds limit")
            spec = json.loads(spec_turn["text"])
            if spec.get("status") == "blocked":
                record["recipe_status"] = "blocked"
                return record
            files = spec.get("files")
            if (
                spec.get("status") != "complete"
                or not isinstance(files, list)
                or not 1 <= len(files) <= 32
            ):
                raise ValueError("invalid headless spec response")
            for name in files:
                path = relative_path(install.workspace, name)
                if (
                    not any(
                        name.startswith(root + "/")
                        for root in install.manifest["control_paths"]
                    )
                    or not path.is_file()
                ):
                    raise ValueError("spec response names a non-control artifact")
            kernels = [name for name in files if name.endswith("/SPEC.md")]
            if len(kernels) != 1:
                raise ValueError("one authoritative spec kernel required")
            folder = relative_path(install.workspace, kernels[0]).parent
            planner = "planner-" + uuid.uuid4().hex
            run.session.new_thread(planner)
            plan_turn = run.session.turn(
                planner,
                f"Read {install.workspace / kernels[0]}, its companions, and TASK.md. "
                "You are the added recipe planner, not BMAD's interactive Story Breakdown. "
                "Choose the smallest ordered set of independently verifiable increments for the known request. "
                "Prefer one when sufficient; at most four. Do not invent future scope. Keep each intent to two sentences. "
                'Return only JSON: {"increments":[{"id":"one","intent":"...","acceptance":["observable check"],"depends_on":[]}]}. '
                "Dependencies reference earlier IDs. IDs contain lowercase letters, digits and dashes and must be prefix-free. "
                "The caller will publish these as explicitly recipe-authored story entries; you have read-only access.",
            )
            record.update(plan_turn=plan_turn, turn=plan_turn)
            if plan_turn["status"] != "completed":
                return record
            increments = parse_plan(plan_turn["text"])
            record["plan"] = increments
            story_path = folder / "stories.yaml"
            existing = []
            if story_path.exists():
                if story_path.is_symlink() or story_path.stat().st_size > 65536:
                    raise ValueError("untrusted or oversized caller story file")
                existing = json.loads(story_path.read_text())
                if not isinstance(existing, list) or len(existing) > 20:
                    raise ValueError("unsupported prior caller story file")
            prefix = "r" + uuid.uuid4().hex[:12]
            stories = [
                {
                    "id": prefix + "-" + item["id"],
                    "title": item["intent"].splitlines()[0][:120],
                    "description": item["intent"],
                    "invoke_dev_with": "Acceptance obligations: "
                    + json.dumps(item["acceptance"]),
                }
                for item in increments
            ]
            identities = [story["id"] for story in [*existing, *stories]]
            if (
                any(
                    not isinstance(identity, str)
                    or not re.fullmatch("[a-zA-Z0-9-]{1,96}", identity)
                    for identity in identities
                )
                or len(set(identities)) != len(identities)
                or any(
                    a.startswith(b + "-")
                    for a in identities
                    for b in identities
                    if a != b
                )
            ):
                raise ValueError("caller story identities collide")
            encoded = json.dumps([*existing, *stories], indent=2)
            if len(encoded.encode()) > 65536:
                raise ValueError("caller story file exceeds limit")
            # JSON is valid YAML. This is explicitly caller-added orchestration,
            # not an output attributed to headless bmad-spec Story Breakdown.
            story_path.write_text(encoded + "\n")
            record.update(
                story_file=story_path.relative_to(install.workspace).as_posix(),
                story_author="added recipe planner",
            )
            for increment, story in zip(increments, stories):
                dispatch = BmadDispatch(run, install).invoke(
                    f"Dispatch story id {story['id']} from spec folder {folder}. "
                    "Use stock folder+id routing. Additional caller planning context: "
                    + story["invoke_dev_with"]
                )
                matches = list((folder / "stories").glob(story["id"] + "-*.md"))
                if len(matches) > 1:
                    raise ValueError("ambiguous authoritative story spec")
                claim = (
                    spec_claim(
                        install, matches[0].relative_to(install.workspace).as_posix()
                    )
                    if matches
                    else None
                )
                record["increments"].append(
                    {
                        "id": increment["id"],
                        "story_id": story["id"],
                        "spec_claim": claim,
                        "dispatch": dispatch,
                    }
                )
                record["turn"] = dispatch["turn"]
                if dispatch["turn"]["status"] != "completed":
                    return record
                status = claim["status_claim"] if claim else "unknown"
                if status != "done":
                    record["recipe_status"] = (
                        "blocked" if status == "blocked" else "unknown"
                    )
                    return record
            record["recipe_status"] = "completed"
            return record
        except Exception as error:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error)[:2048],
            }
            raise
        finally:
            target.write_text(json.dumps(record, indent=2) + "\n")
            install.verify()
