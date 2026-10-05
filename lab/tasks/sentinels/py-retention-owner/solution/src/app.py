from copy import deepcopy


def run(data):
    now = data["now_day"]
    return [
        deepcopy(record)
        for record in data["records"]
        if record.get("legal_hold", False) or now - record["created_day"] <= 30
    ]
