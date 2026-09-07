import json
from versions import order

def run(argv, stdin):
    if argv:
        raise ValueError("usage: stdin versions")
    return order(json.loads(stdin))
