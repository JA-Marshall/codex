from copy import deepcopy
from orders import reserve, cancel
from report import report


def run(data):
    state = deepcopy(data["state"])
    results = []
    for operation in data["operations"]:
        try:
            if operation["op"] == "reserve":
                reserve(state, operation)
            elif operation["op"] == "cancel":
                cancel(state, operation["id"])
            else:
                raise ValueError("unsupported-operation")
            results.append("ok")
        except ValueError as error:
            results.append(str(error))
    return {"state": state, "results": results, "summary": report(state)}
