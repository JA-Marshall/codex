import json
from pathlib import Path
from network import read_graph
from routing import shortest

def run(argv, stdin):
    if len(argv) != 1:
        raise ValueError("usage: GRAPH")
    nodes, adjacency = read_graph(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
    queries = json.loads(stdin)
    if not isinstance(queries, list):
        raise ValueError("invalid queries")
    for query in queries:
        if not isinstance(query, list) or len(query) != 2 or any(not isinstance(name, str) for name in query):
            raise ValueError("invalid queries")
        if any(name not in nodes for name in query):
            raise ValueError("unknown node")
    return [shortest(adjacency, start, end) for start, end in queries]
