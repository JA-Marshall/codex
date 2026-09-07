import re

def validate(entries):
    if not isinstance(entries, list):
        raise ValueError("invalid manifest")
    seen = set()
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {"id", "path", "sha256"}
                or not isinstance(entry["id"], str) or not entry["id"] or entry["id"] in seen
                or not isinstance(entry["path"], str) or not entry["path"]
                or not isinstance(entry["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("invalid manifest")
        seen.add(entry["id"])
    return entries
