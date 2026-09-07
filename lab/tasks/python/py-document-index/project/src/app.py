from index_store import build, query

def run(argv, stdin):
    if len(argv) == 3 and argv[0] == "build":
        return build(argv[1], argv[2])
    if len(argv) >= 3 and argv[0] == "query":
        return query(argv[1], " ".join(argv[2:]))
    raise ValueError("usage: build ROOT INDEX | query INDEX TEXT")
