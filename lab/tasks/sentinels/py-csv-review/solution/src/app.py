import csv
import io


def run(request):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["sku", "label"])
    for row in request["rows"]:
        if not isinstance(row["sku"], str) or not isinstance(row["label"], str):
            raise ValueError("fields must be strings")
        writer.writerow([row["sku"], row["label"]])
    return output.getvalue()
