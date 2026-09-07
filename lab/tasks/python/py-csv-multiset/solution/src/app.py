from reconcile import compare

def run(argv, stdin):
    if len(argv) != 2:
        raise ValueError("usage: BEFORE AFTER")
    return compare(argv[0], argv[1])
