"""Aggregate counts from CSV text."""


def summarize(text: str) -> dict[str, int]:
    lines = text.splitlines()
    if not lines:
        return {}
    if lines[0] != "category,count":
        raise ValueError("expected category,count header")
    totals = {}
    for line in lines[1:]:
        if not line:
            continue
        category, count = line.split(",")
        totals[category] = totals.get(category, 0) + int(count)
    return totals
