def run(data):
    subtotal = sum(item["unit_price"] * item["quantity"] for item in data["items"])
    if "coupon" not in data:
        shipping = 0 if subtotal >= 5000 else 500
        return {
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
        }
    eligible = sum(
        item["unit_price"] * item["quantity"]
        for item in data["items"]
        if item["category"] != "gift-card"
    )
    discount = min(data["coupon"], eligible)
    shipping = 0 if subtotal >= 5000 else 500
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "total": subtotal - discount + shipping,
    }
