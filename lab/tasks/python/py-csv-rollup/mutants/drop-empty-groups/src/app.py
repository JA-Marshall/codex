from report import rows, rollup

def run(argv, stdin):
    if len(argv) == 2 and argv[0] == "rows":
        return rows(argv[1])
    if len(argv) == 4 and argv[0] == "rollup":
        return rollup(argv[1], argv[2], argv[3])
    raise ValueError("usage: rows FILE | rollup FILE GROUP VALUE")
