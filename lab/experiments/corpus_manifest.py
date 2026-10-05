"""Opaque corpus metadata and development-only input binding.

This validates declared ancestry, not semantic independence or custodian honesty.
Held-out paths, briefs, cases and reference implementations are absent by design.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from task_registry import inventory

TARGETS = {"development": 24, "validation": 12, "confirmation": 24}
ID = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value)


def valid_hash(value):
    return isinstance(value, str) and SHA.fullmatch(value)


def validate_index(data):
    fields = {
        "schema_version",
        "id",
        "state",
        "development_root",
        "custodian_seal_sha256",
        "entries",
    }
    if (
        not isinstance(data, dict)
        or set(data) != fields
        or data["schema_version"] != 1
        or not valid_id(data["id"])
    ):
        raise ValueError("invalid corpus index identity")
    if data["state"] not in ("draft", "sealed") or not valid_id(
        data["development_root"]
    ):
        raise ValueError("invalid corpus state or development directory")
    if data["custodian_seal_sha256"] is not None and not valid_hash(
        data["custodian_seal_sha256"]
    ):
        raise ValueError("invalid custodian seal fingerprint")
    entries = data["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ValueError("corpus needs 1..100 metadata entries")
    entry_fields = {
        "id",
        "project_id",
        "lineage_id",
        "duplicate_family",
        "split",
        "track",
        "cohort",
        "owner_diagnostic",
        "content_sha256",
        "calibration_sha256",
        "provenance",
    }
    provenance_fields = {
        "origin",
        "origin_fingerprint",
        "revision_fingerprint",
        "exposed_to_tuning",
    }
    seen, ancestry, counts, diagnostics, projects = set(), {}, Counter(), Counter(), {}
    parents, owners, primary = {}, {}, []

    def ancestor(identity):
        while parents[identity] != identity:
            parents[identity] = parents[parents[identity]]
            identity = parents[identity]
        return identity

    for item in entries:
        if (
            not isinstance(item, dict)
            or set(item) != entry_fields
            or any(
                not valid_id(item[key])
                for key in ("id", "project_id", "lineage_id", "duplicate_family")
            )
        ):
            raise ValueError("invalid opaque corpus entry")
        if item["id"] in seen:
            raise ValueError("duplicate corpus task ID")
        seen.add(item["id"])
        parents[item["id"]] = item["id"]
        if (
            item["split"] not in TARGETS
            or item["track"] not in ("A", "B")
            or item["cohort"] not in ("primary", "diagnostic")
            or type(item["owner_diagnostic"]) is not bool
        ):
            raise ValueError("invalid corpus split, track or cohort")
        if item["owner_diagnostic"] and (
            item["cohort"] != "diagnostic" or item["track"] != "A"
        ):
            raise ValueError("owner diagnostic cannot satisfy clear-A primary quota")
        provenance = item["provenance"]
        if (
            not isinstance(provenance, dict)
            or set(provenance) != provenance_fields
            or provenance["origin"]
            not in ("private-authored", "public-repository", "synthetic")
            or type(provenance["exposed_to_tuning"]) is not bool
            or any(
                not valid_hash(provenance[key])
                for key in ("origin_fingerprint", "revision_fingerprint")
            )
        ):
            raise ValueError("invalid bounded provenance")
        if item["split"] != "development" and provenance["exposed_to_tuning"]:
            raise ValueError("tuning-exposed project cannot enter held-out splits")
        for key in ("content_sha256", "calibration_sha256"):
            if item[key] is not None and not valid_hash(item[key]):
                raise ValueError("invalid input or calibration fingerprint")
            if data["state"] == "sealed" and item[key] is None:
                raise ValueError(
                    "sealed corpus requires calibrated content commitments"
                )
        identities = [
            (key, item[key]) for key in ("project_id", "lineage_id", "duplicate_family")
        ]
        identities.append(("origin", provenance["origin_fingerprint"]))
        if item["content_sha256"] is not None:
            identities.append(("content", item["content_sha256"]))
        for identity in identities:
            prior = ancestry.setdefault(identity, item["split"])
            if prior != item["split"]:
                raise ValueError(
                    "project, declared lineage, duplicate family or content crosses splits"
                )
            first = owners.setdefault(identity, item["id"])
            parents[ancestor(item["id"])] = ancestor(first)
        if item["cohort"] == "primary":
            counts[(item["split"], item["track"])] += 1
            projects.setdefault(item["split"], set()).add(item["project_id"])
            primary.append(item)
        else:
            diagnostics[item["split"]] += 1
    for split, target in TARGETS.items():
        for track in ("A", "B"):
            actual = counts[(split, track)]
            if actual > target // 2 or (
                data["state"] == "sealed" and actual != target // 2
            ):
                raise ValueError(
                    "primary corpus requires 24/12/24, half clear A and half B"
                )
    clusters = {
        split: len({ancestor(item["id"]) for item in primary if item["split"] == split})
        for split in TARGETS
    }
    if data["state"] == "sealed" and (
        clusters["confirmation"] != 24 or data["custodian_seal_sha256"] is None
    ):
        raise ValueError(
            "confirmation requires 24 independent declared projects and custodian seal"
        )
    return {
        "id": data["id"],
        "state": data["state"],
        "primary": {
            split: {track: counts[(split, track)] for track in ("A", "B")}
            for split in TARGETS
        },
        "diagnostics": dict(diagnostics),
        "declared_projects": {split: len(value) for split, value in projects.items()},
        "declared_ancestry_clusters": clusters,
        "semantic_independence": "requires provenance review; hashes and declarations alone do not prove it",
    }


def load_index(path):
    path = Path(path)
    if (
        path.absolute() != path.resolve(strict=True)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 256 * 1024
    ):
        raise ValueError("corpus index must be a bounded regular metadata file")
    data = json.loads(path.read_text())
    validate_index(data)
    return data


def bind_development(path, task_root, tasks=None):
    """Resolve only the development directory; no held-out locator is accepted."""
    path = Path(path)
    data = load_index(path)
    path = path.resolve(strict=True)
    declared = path.parent / data["development_root"]
    if (
        declared.absolute() != declared.resolve(strict=True)
        or Path(task_root).absolute() != Path(task_root).resolve(strict=True)
        or declared.resolve(strict=True) != Path(task_root).resolve(strict=True)
    ):
        raise ValueError("tuning task root must be the corpus development directory")
    if tasks is not None:
        expected = {
            item["id"]: item
            for item in data["entries"]
            if item["split"] == "development"
        }
        for name, task in tasks.items():
            entry = expected.get(name)
            if (
                entry is None
                or task.manifest["split"] != "development"
                or task.manifest["project_id"] != entry["project_id"]
                or task.manifest.get("track") != entry["track"]
            ):
                raise ValueError("development task identity differs from corpus index")
            owner = "owner-clarification" in task.manifest["capabilities"]
            if owner != entry["owner_diagnostic"] and task.manifest.get("track") == "A":
                raise ValueError("owner diagnostic classification differs")
            if (
                entry["content_sha256"] != fingerprint(inventory(task.root))
                or entry["calibration_sha256"] is None
            ):
                raise ValueError(
                    "development task needs matching calibrated content commitment"
                )
            from corpus_calibration import verify_certificate

            verify_certificate(
                path.parent / "certificates" / (name + ".json"), entry, task
            )
    return data


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("validate")
    command.add_argument("index", type=Path)
    command = sub.add_parser("certify-development")
    for name in ("task", "authoring", "calibration", "output"):
        command.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.action == "validate":
        print(json.dumps(validate_index(load_index(args.index)), indent=2))
    else:
        from corpus_calibration import certify_development

        print(
            certify_development(
                args.task, args.authoring, args.calibration, args.output
            )
        )


if __name__ == "__main__":
    main()
