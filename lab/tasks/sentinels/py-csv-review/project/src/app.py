def run(request):
    return "sku,label\n" + "".join(
        row["sku"] + "," + row["label"] + "\n" for row in request["rows"]
    )
