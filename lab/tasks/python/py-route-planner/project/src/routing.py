import heapq

def shortest(adjacency, start, end):
    queue = [(0, (start,))]
    best = {start: (0, (start,))}
    while queue:
        cost, path = heapq.heappop(queue)
        node = path[-1]
        if (cost, path) != best[node]:
            continue
        if node == end:
            return {"cost": cost, "path": list(path)}
        for target, weight in adjacency[node]:
            candidate = (cost + weight, path + (target,))
            if target == end:
                return {"cost": candidate[0], "path": list(candidate[1])}
            if target not in best or candidate < best[target]:
                best[target] = candidate
                heapq.heappush(queue, candidate)
    return {"cost": None, "path": []}
