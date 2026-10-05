from copy import deepcopy


def run(request):
    items = deepcopy(request["items"])
    for action in request.get("actions", []):
        if action["op"] not in ("archive", "restore"):
            raise ValueError("operation is not supported: " + action["op"])
        item = next((item for item in items if item["id"] == action["id"]), None)
        if item is None:
            raise ValueError("no record has identifier " + action["id"])
        active = action["op"] == "restore"
        if item["active"] != active:
            item["active"] = active
            item.setdefault("events", []).append("restored" if active else "archived")
    return {"items": items, "visible": [item["id"] for item in items if item["active"]]}
