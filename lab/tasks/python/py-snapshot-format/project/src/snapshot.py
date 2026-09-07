import json
from pathlib import Path

def read(filename):
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    values = {}
    if not isinstance(data, list):
        raise ValueError("invalid snapshot")
    for item in data:
        if not isinstance(item, dict) or set(item) != {"key", "value"} or not isinstance(item["key"], str):
            raise ValueError("invalid snapshot")
        values[item["key"]] = item["value"]
    return values

def compact(filename):
    values = read(filename)
    rows = [{"key": key, "value": values[key]} for key in sorted(values)]
    Path(filename).write_text(json.dumps(rows) + "\n", encoding="utf-8", newline="\n")
    return {"keys": len(values)}
