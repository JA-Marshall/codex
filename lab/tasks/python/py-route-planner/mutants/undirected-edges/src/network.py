def read_graph(data):
    if not isinstance(data, dict) or set(data) != {"nodes", "edges"}:
        raise ValueError("invalid graph")
    nodes, edges = data["nodes"], data["edges"]
    if (not isinstance(nodes, list) or any(not isinstance(node, str) or not node for node in nodes)
            or len(set(nodes)) != len(nodes) or not isinstance(edges, list)):
        raise ValueError("invalid graph")
    adjacency = {node: [] for node in nodes}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "cost"}:
            raise ValueError("invalid edge")
        if (not isinstance(edge["from"], str) or edge["from"] not in adjacency
                or not isinstance(edge["to"], str) or edge["to"] not in adjacency
                or type(edge["cost"]) is not int or edge["cost"] <= 0):
            raise ValueError("invalid edge")
        adjacency[edge["from"]].append((edge["to"], edge["cost"]))
        adjacency[edge["to"]].append((edge["from"], edge["cost"]))
    return set(nodes), adjacency
