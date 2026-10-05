def report(state):
    reserved = {sku: 0 for sku in state["stock"]}
    for order in state["orders"].values():
        if order["status"] == "reserved":
            reserved[order["sku"]] += order["quantity"]
    return {"available": dict(state["stock"]), "reserved": reserved}
