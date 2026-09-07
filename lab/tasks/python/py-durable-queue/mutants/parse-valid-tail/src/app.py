import json
from queue_store import execute

def run(argv, stdin):
    if len(argv) != 2:
        raise ValueError("usage: COMMAND LOG")
    return execute(argv[0], argv[1], json.loads(stdin) if stdin.strip() else {})
