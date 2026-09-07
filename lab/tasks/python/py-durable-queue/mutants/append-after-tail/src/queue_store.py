import json
from pathlib import Path
from replay import replay

def load(filename):
    path = Path(filename)
    raw = path.read_bytes() if path.exists() else b""
    complete = raw[:raw.rfind(b"\n") + 1]
    try:
        events = [json.loads(line) for line in complete.decode("utf-8").split("\n")[:-1]]
    except (ValueError, UnicodeError):
        raise ValueError("corrupt log") from None
    pending, seen = replay(events)
    return complete, pending, seen

def execute(command, filename, request):
    complete, pending, seen = load(filename)
    if command == "list":
        return pending
    if command == "push":
        if not isinstance(request, dict) or set(request) != {"id", "value"} or not isinstance(request["id"], str) or not request["id"]:
            raise ValueError("invalid item")
        if request["id"] in seen:
            raise ValueError("duplicate id")
        event = {"op": "push", **request}
        result = {"ok": True}
    elif command == "pop":
        if not pending:
            return None
        result = pending[0]
        event = {"op": "pop", "id": result["id"]}
    else:
        raise ValueError("unknown command")
    encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    Path(filename).write_bytes((Path(filename).read_bytes() if Path(filename).exists() else b"") + encoded)
    return result
