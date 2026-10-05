def apply_changes(stock, changes):
    candidate = stock.copy()
    for change in changes:
        sku, delta = change["sku"], change["delta"]
        if sku not in candidate:
            raise ValueError("unknown-sku")
        if type(delta) is not int:
            raise ValueError("invalid-delta")
        candidate[sku] = stock[sku] + delta
    if any(value < 0 for value in candidate.values()):
        raise ValueError("negative-stock")
    return candidate


def run(request):
    stock = request["stock"].copy()
    results = []
    for command in request["commands"]:
        try:
            if command["op"] == "adjust":
                changes = [{"sku": command["sku"], "delta": command["delta"]}]
            elif command["op"] == "batch":
                changes = command["changes"]
            else:
                raise ValueError("unsupported-op")
            stock = apply_changes(stock, changes)
            results.append({"ok": True})
        except ValueError as error:
            results.append({"error": str(error)})
    return {"stock": stock, "results": results}
