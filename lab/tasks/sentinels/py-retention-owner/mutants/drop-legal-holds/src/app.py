from copy import deepcopy


def run(data):
    now = data["now_day"]
    return [
        deepcopy(record)
        for record in data["records"]
        if now - record["created_day"] <= 30
    ]
