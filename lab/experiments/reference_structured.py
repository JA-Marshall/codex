"""Calibration references; never copied into live agent task repositories."""

from copy import deepcopy
import heapq


def order_tasks(graph):
    if not isinstance(graph, dict) or any(
        not isinstance(n, str) or not n for n in graph
    ):
        raise ValueError("invalid graph")
    for dependencies in graph.values():
        if not isinstance(dependencies, list) or any(
            not isinstance(d, str) or not d or d not in graph for d in dependencies
        ):
            raise ValueError("invalid dependencies")
    remaining = {node: set(deps) for node, deps in graph.items()}
    ready = [node for node, deps in remaining.items() if not deps]
    heapq.heapify(ready)
    result = []
    while ready:
        node = heapq.heappop(ready)
        result.append(node)
        for dependent, dependencies in remaining.items():
            if node in dependencies:
                dependencies.remove(node)
                if not dependencies:
                    heapq.heappush(ready, dependent)
    if len(result) != len(graph):
        raise ValueError("cycle")
    return result


def merge_config(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        raise ValueError("expected objects")
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
