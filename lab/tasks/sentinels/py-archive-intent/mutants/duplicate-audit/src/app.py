from copy import deepcopy


def run(request):
    items = deepcopy(request["items"])
    for action in request.get("actions", []):
        if action["op"] not in ("archive", "restore"):
            raise ValueError("unsupported action")
        item = next((item for item in items if item["id"] == action["id"]), None)
        if item is None:
            raise ValueError("unknown item")
        active = action["op"] == "restore"
        item["active"] = active
        item.setdefault("events", []).append("restored" if active else "archived")
    return {"items": items, "visible": [item["id"] for item in items if item["active"]]}
