from collections import Counter
from csv_io import read_table

def compare(before, after):
    old_headers, old_rows = read_table(before)
    new_headers, new_rows = read_table(after)
    if set(old_headers) != set(new_headers):
        raise ValueError("schema mismatch")
    columns = sorted(old_headers)
    old = Counter(tuple(row[column] for column in columns) for row in old_rows)
    new = Counter(tuple(row[column] for column in columns) for row in new_rows)

    def render(delta):
        return [{"row": dict(zip(columns, key)), "count": delta[key]} for key in sorted(delta)]

    return {"columns": columns, "removed": render(old - new), "added": render(new - old)}
