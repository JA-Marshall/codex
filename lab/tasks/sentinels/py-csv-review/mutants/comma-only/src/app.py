def run(request):
    def quote(value):
        return '"' + value + '"' if "," in value else value

    return "sku,label\n" + "".join(
        quote(row["sku"]) + "," + quote(row["label"]) + "\n" for row in request["rows"]
    )
