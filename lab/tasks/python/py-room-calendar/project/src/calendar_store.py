import json
from pathlib import Path

def load(filename):
    path = Path(filename)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

def save(filename, bookings):
    ordered = sorted(bookings, key=lambda item: item["id"])
    Path(filename).write_text(json.dumps(ordered, sort_keys=True, separators=(",", ":")) + "\n",
                              encoding="utf-8", newline="\n")

def validate(booking, others):
    if (set(booking) != {"id", "room", "start", "end"}
            or not isinstance(booking["id"], str) or not booking["id"]
            or not isinstance(booking["room"], str) or not booking["room"]
            or type(booking["start"]) is not int or type(booking["end"]) is not int
            or booking["start"] >= booking["end"]):
        raise ValueError("invalid booking")
    if any(item["id"] == booking["id"] for item in others):
        raise ValueError("duplicate id")
    if any(item["room"] == booking["room"] and booking["start"] < item["end"]
           and item["start"] < booking["end"] for item in others):
        raise ValueError("conflict")

def execute(command, filename, request):
    bookings = load(filename)
    if command == "list":
        return sorted(bookings, key=lambda item: (item["room"], item["start"], item["id"]))
    if command == "add":
        validate(request, bookings)
        bookings.append(request)
    else:
        raise ValueError("unknown command")
    save(filename, bookings)
    return {"ok": True}
