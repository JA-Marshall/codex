def plan(tasks):
    if not isinstance(tasks, dict) or any(not isinstance(k, str) or not isinstance(v, list)
                                         or any(not isinstance(d, str) for d in v)
                                         for k, v in tasks.items()):
        raise ValueError("invalid graph")
    dependencies = {key: set(value) for key, value in tasks.items()}
    missing = sorted(set().union(*dependencies.values()) - dependencies.keys()) if tasks else []
    if missing:
        raise ValueError("unknown dependency: " + missing[0])
    pending = set(tasks)
    done = set()
    waves = []
    while pending:
        ready = sorted(node for node in pending if dependencies[node] <= done)
        if not ready:
            raise ValueError("cycle")
        ready = ready[:1]
        waves.append(ready)
        pending.difference_update(ready)
        done.update(ready)
    return {"waves": waves, "tasks": len(tasks)}
