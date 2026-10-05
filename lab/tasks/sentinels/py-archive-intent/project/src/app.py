def run(request):
    items = request["items"]
    return {"items": items, "visible": [item["id"] for item in items if item["active"]]}
