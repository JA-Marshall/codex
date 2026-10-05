def run(data):
    subtotal = sum(item["unit_price"] * item["quantity"] for item in data["items"])
    shipping = 0 if subtotal >= 5000 else 500
    return {"subtotal": subtotal, "shipping": shipping, "total": subtotal + shipping}
