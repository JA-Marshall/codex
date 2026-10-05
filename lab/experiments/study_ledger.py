"""Append-only study attempts; an absent terminal record means unfinished/unknown."""

import json
import os
from pathlib import Path
import re
import time
import uuid

from campaign_inputs import digest, read_json


def append_record(directory, kind, value):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record = dict(
        schema_version=1, kind=kind, unix_ms=time.time_ns() // 1000000, **value
    )
    encoded = (json.dumps(record, indent=2) + "\n").encode()
    if len(encoded) > 65536:
        raise ValueError("ledger record exceeds64KiB")
    target = directory / (str(time.time_ns()) + "-" + uuid.uuid4().hex + ".json")
    with target.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def validate_variant(value, registry=None):
    if not isinstance(value, dict) or set(value) != {
        "id",
        "parent",
        "hypothesis",
        "change",
    }:
        raise ValueError("variant requires id, parent, hypothesis and change")
    if not isinstance(value["id"], str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,63}", value["id"]
    ):
        raise ValueError("variant ID must be a short stable lowercase identifier")
    if any(
        not isinstance(value[name], str) or not 1 <= len(value[name]) <= 4096
        for name in ("hypothesis", "change")
    ):
        raise ValueError("variant hypothesis and change must be explicit and bounded")
    registry = Path(registry).resolve() if registry is not None else None
    parent = value["parent"]
    if parent is not None and (
        not isinstance(parent, str)
        or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", parent)
        or (registry is not None and not (registry / parent / "variant.json").is_file())
    ):
        raise ValueError("variant parent must already be registered")
    if registry is not None and (registry / value["id"]).exists():
        raise FileExistsError("variant identity is already registered")


def register_variant(registry, value, manifest_path):
    validate_variant(value, registry)
    registry = Path(registry).resolve()
    manifest = read_json(manifest_path)
    record = dict(
        schema_version=1,
        **value,
        campaign_manifest=str(Path(manifest_path).resolve()),
        campaign_sha256=digest(manifest_path),
        input_pins=manifest["pins"],
    )
    target = registry / value["id"]
    target.mkdir(parents=True, exist_ok=False)
    with (target / "variant.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    append_record(
        target / "attempts",
        "prepared",
        {"campaign_sha256": record["campaign_sha256"], "model_calls": 0},
    )
    return target
