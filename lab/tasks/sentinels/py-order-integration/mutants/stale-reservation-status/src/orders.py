def reserve(state, operation):
    identity, sku, quantity = operation["id"], operation["sku"], operation["quantity"]
    if identity in state["orders"] or type(quantity) is not int or quantity <= 0:
        raise ValueError("invalid-order")
    if sku not in state["stock"] or state["stock"][sku] < quantity:
        raise ValueError("unavailable")
    state["stock"][sku] -= quantity
    state["orders"][identity] = {"sku": sku, "quantity": quantity, "status": "reserved"}


def cancel(state, identity):
    if identity not in state["orders"]:
        raise ValueError("unknown-order")
    order = state["orders"][identity]
    if order["status"] == "reserved":
        state["stock"][order["sku"]] += order["quantity"]
