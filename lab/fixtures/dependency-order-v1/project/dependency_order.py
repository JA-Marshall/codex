"""Order tasks for execution."""


def order_tasks(graph: dict[str, list[str]]) -> list[str]:
    return sorted(graph)
