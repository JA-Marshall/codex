def report(state):
    return {
        "available": dict(state["stock"]),
        "reserved": {sku: 0 for sku in state["stock"]},
    }
