import json
from graph import plan

def run(argv, stdin):
    if argv:
        raise ValueError("usage: stdin JSON")
    return plan(json.loads(stdin))
