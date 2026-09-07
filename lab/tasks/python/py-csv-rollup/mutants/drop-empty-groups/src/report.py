import csv

def rows(filename):
    with open(filename, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))
def rollup(filename, group, value):
    with open(filename, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if group not in (reader.fieldnames or []) or value not in (reader.fieldnames or []):
            raise ValueError("unknown column")
        totals = {}
        for row in reader:
            if not row[group]:
                continue
            try:
                number = int(row[value])
            except (TypeError, ValueError):
                raise ValueError("invalid integer") from None
            bucket = totals.setdefault(row[group], {"count": 0, "sum": 0})
            bucket["count"] += 1
            bucket["sum"] += number
    return [{"group": key, **totals[key]} for key in sorted(totals)]
