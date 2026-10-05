"""Small, source-preserving roadmaps and portable kickoff prompts."""

import hashlib
import json
from pathlib import Path
import re

from workflows.bmad_orchestrated import parse_plan


def source_contains(source, quote):
    """Allow single LF/CRLF prose wraps; preserve inline and paragraph spacing.

    This checks textual anchoring, not semantic equivalence. Keep the original
    strings in all artifacts and hashes; never normalize the accepted scope.
    """

    def soft_wraps(value):
        parts = re.split(r"(\r?\n)", value)
        for index in range(1, len(parts), 2):
            if parts[index - 1].strip(" \t") and parts[index + 1].strip(" \t"):
                parts[index] = " "
        return "".join(parts)

    return soft_wraps(quote) in soft_wraps(source)


def propose(
    intent,
    response,
    *,
    previous=None,
    discovery=None,
    completed=(),
    owner_followup=None,
):
    if not isinstance(intent, str) or not 1 <= len(intent.encode()) <= 32768:
        raise ValueError("bounded source intent required")
    if not isinstance(response, str) or len(response.encode()) > 32768:
        raise ValueError("bounded roadmap response required")
    if previous is not None:
        if previous["source_intent"] != intent:
            raise ValueError("a roadmap revision cannot replace original intent")
        if (
            hashlib.sha256(
                json.dumps(
                    {key: val for key, val in previous.items() if key != "sha256"},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            != previous["sha256"]
        ):
            raise ValueError("prior roadmap fingerprint differs")
    followups = list((previous or {}).get("owner_followups", []))
    if owner_followup is not None:
        if (
            previous is None
            or not isinstance(owner_followup, str)
            or not 1 <= len(owner_followup.encode()) <= 4096
            or len(followups) >= 4
        ):
            raise ValueError(
                "bounded explicit owner follow-up requires a prior roadmap"
            )
        followups.append(owner_followup)
    value = json.loads(response)
    fields = {
        "requirements",
        "increments",
        "open_questions",
        "assumptions",
        "exclusions",
        "repository_evidence",
        "decision_boundary",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(
            "roadmap requires source obligations, increments and decision context"
        )
    for name in ("open_questions", "assumptions", "exclusions", "repository_evidence"):
        items = value[name]
        if (
            not isinstance(items, list)
            or len(items) > 8
            or any(
                not isinstance(item, str) or not 1 <= len(item.encode()) <= 1024
                for item in items
            )
        ):
            raise ValueError("invalid bounded decision context")
    if (
        not isinstance(value["decision_boundary"], str)
        or not 1 <= len(value["decision_boundary"].encode()) <= 2048
    ):
        raise ValueError("explicit decision boundary required")
    requirements = value["requirements"]
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 24:
        raise ValueError("bounded stable requirements required")
    ids = set()
    for item in requirements:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "source_quote", "acceptance"}
            or not isinstance(item["id"], str)
            or not re.fullmatch("r-[a-z0-9-]{1,60}", item["id"])
            or item["id"] in ids
            or not isinstance(item["source_quote"], str)
            or not item["source_quote"].strip()
            or not any(
                source_contains(source, item["source_quote"])
                for source in [intent, *followups]
            )
            or len(item["source_quote"].encode()) > 2048
            or not isinstance(item["acceptance"], list)
            or not 1 <= len(item["acceptance"]) <= 8
            or any(
                not isinstance(check, str) or not 1 <= len(check.encode()) <= 512
                for check in item["acceptance"]
            )
        ):
            raise ValueError("invalid source-grounded requirement")
        ids.add(item["id"])
    increments = value["increments"]
    if not isinstance(increments, list) or any(
        not isinstance(item, dict)
        or set(item) != {"id", "intent", "acceptance", "depends_on", "requirement_ids"}
        for item in increments
    ):
        raise ValueError("increments must map source requirements")
    parse_plan(
        json.dumps(
            {
                "increments": [
                    {key: val for key, val in item.items() if key != "requirement_ids"}
                    for item in increments
                ]
            }
        )
    )
    covered = set()
    for item in increments:
        refs = item["requirement_ids"]
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or ref not in ids for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            raise ValueError("invalid requirement mapping")
        covered.update(refs)
    if covered != ids:
        raise ValueError("roadmap drops a source obligation")
    revision, prior = 1, None
    if previous is not None:
        if previous["source_intent"] != intent:
            raise ValueError("a roadmap revision cannot replace original intent")
        if not isinstance(discovery, str) or not 1 <= len(discovery.encode()) <= 4096:
            raise ValueError(
                "revision requires concrete discovery or explicit follow-up request"
            )
        count = len(previous["requirements"])
        if requirements[:count] != previous["requirements"] or (
            len(requirements) > count and owner_followup is None
        ):
            raise ValueError("revision cannot weaken or replace requirement acceptance")
        if any(
            not source_contains(owner_followup, item["source_quote"])
            for item in requirements[count:]
        ):
            raise ValueError("new requirements must cite the explicit owner follow-up")
        old = {item["id"]: item for item in previous["increments"]}
        new = {item["id"]: item for item in increments}
        if len(set(completed)) != len(completed) or any(
            identity not in old or new.get(identity) != old[identity]
            for identity in completed
        ):
            raise ValueError(
                "completed increment and prerequisites must remain unchanged"
            )
        if not set(previous.get("completed", [])) <= set(completed):
            raise ValueError("completed history cannot disappear")
        revision, prior = previous["revision"] + 1, previous["sha256"]
    elif discovery is not None or completed:
        raise ValueError("discovery belongs to an existing roadmap")
    record = {
        "schema_version": 1,
        "revision": revision,
        "previous_sha256": prior,
        "source_intent": intent,
        "source_sha256": hashlib.sha256(intent.encode()).hexdigest(),
        "discovery": discovery,
        **value,
        "completed": list(completed),
        "owner_followups": followups,
        "authority": "Planner proposal; original user intent remains authoritative. Open product questions require owner resolution.",
    }
    record["sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True).encode()
    ).hexdigest()
    return record


def kickoff(roadmap, identity):
    item = next(
        (entry for entry in roadmap["increments"] if entry["id"] == identity), None
    )
    if item is None:
        raise ValueError("unknown increment")
    return (
        f"Implement increment {identity} from roadmap revision {roadmap['revision']} ({roadmap['sha256']}).\n\n"
        "Original user intent (authoritative; preserve its acceptance examples and constraints):\n"
        + roadmap["source_intent"]
        + "\n\nIncrement outcome:\n"
        + item["intent"]
        + "\n\nExplicit owner follow-ups:\n"
        + "\n".join(roadmap["owner_followups"])
        + "\n\nVisible acceptance checks:\n"
        + "\n".join("- " + check for check in item["acceptance"])
        + "\n\nWhole-project source obligations and preserved acceptance (not all must be implemented in this increment):\n"
        + json.dumps(
            [
                requirement
                for requirement in roadmap["requirements"]
                if requirement["id"] in item["requirement_ids"]
            ]
        )
        + "\n\nDeferred later outcomes; do not implement them in this increment:\n"
        + json.dumps(
            [
                {"id": entry["id"], "outcome": entry["intent"]}
                for entry in roadmap["increments"][
                    roadmap["increments"].index(item) + 1 :
                ]
            ]
        )
        + "\n\nPrerequisites: "
        + (", ".join(item["depends_on"]) or "none")
        + "\nRecent discovery or follow-up: "
        + (roadmap["discovery"] or "none")
        + "\nUnresolved product questions:\n"
        + ("\n".join(roadmap["open_questions"]) or "none recorded")
        + "\nAssumptions: "
        + json.dumps(roadmap["assumptions"])
        + "\nExplicit exclusions: "
        + json.dumps(roadmap["exclusions"])
        + "\nCurrent repository evidence: "
        + json.dumps(roadmap["repository_evidence"])
        + "\nDecision boundary: "
        + roadmap["decision_boundary"]
        + "\n\nInspect the current repository before choosing an implementation. Keep the change to this outcome; "
        "do not build later increments or invent future abstractions. Resolve ordinary technical choices within scope. "
        "Ask the owner if an unresolved product decision affects this increment; do not invent an answer. "
        "Return the patch, actual verification results, limitations, and discoveries that change remaining work. "
        "Never weaken original acceptance to make implementation pass.\n"
    )


def export(roadmap, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "roadmap.json").write_text(
        json.dumps(roadmap, indent=2) + "\n", encoding="utf-8"
    )
    for item in roadmap["increments"]:
        (destination / (item["id"] + ".md")).write_text(
            kickoff(roadmap, item["id"]), encoding="utf-8"
        )
    return destination
