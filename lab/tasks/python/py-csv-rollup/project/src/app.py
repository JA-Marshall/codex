from report import rows

def run(argv, stdin):
    if len(argv) == 2 and argv[0] == "rows":
        return rows(argv[1])
    raise ValueError("usage: rows FILE")
