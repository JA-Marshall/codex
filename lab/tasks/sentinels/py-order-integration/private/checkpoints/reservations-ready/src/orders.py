def reserve(state, operation):
    identity, sku, quantity = operation["id"], operation["sku"], operation["quantity"]
    if identity in state["orders"] or type(quantity) is not int or quantity <= 0:
        raise ValueError("invalid-order")
    if sku not in state["stock"] or state["stock"][sku] < quantity:
        raise ValueError("unavailable")
    state["stock"][sku] -= quantity
    state["orders"][identity] = {"sku": sku, "quantity": quantity, "status": "reserved"}
