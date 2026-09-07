from snapshot import read, compact

def run(argv, stdin):
    if len(argv) != 2:
        raise ValueError("usage: read FILE | compact FILE")
    if argv[0] == "read":
        return read(argv[1])
    if argv[0] == "compact":
        return compact(argv[1])
    raise ValueError("usage: read FILE | compact FILE")
