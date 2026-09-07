import json
from pathlib import Path

def read(filename):
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if set(data) != {"version", "values"} or type(data["version"]) is not int or data["version"] != 2 or not isinstance(data["values"], dict):
            raise ValueError("invalid snapshot")
        return data["values"]
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
    values = {key: value for key, value in values.items() if value}
    payload = {"version": 2, "values": values}
    Path(filename).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                              encoding="utf-8", newline="\n")
    return {"keys": len(values)}
