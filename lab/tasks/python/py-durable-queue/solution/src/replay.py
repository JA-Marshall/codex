def replay(events):
    pending = []
    seen = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("corrupt log")
        if event.get("op") == "push":
            if set(event) != {"op", "id", "value"} or not isinstance(event["id"], str) or not event["id"] or event["id"] in seen:
                raise ValueError("corrupt log")
            pending.append({"id": event["id"], "value": event["value"]})
            seen.add(event["id"])
        elif event.get("op") == "pop":
            if set(event) != {"op", "id"} or not pending or pending[0]["id"] != event["id"]:
                raise ValueError("corrupt log")
            pending.pop(0)
        else:
            raise ValueError("corrupt log")
    return pending, seen
