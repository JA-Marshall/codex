import json
from pathlib import Path

def load(filename):
    path = Path(filename)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"balances": {}, "receipts": {}}

def save(filename, state):
    Path(filename).write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
                              encoding="utf-8", newline="\n")
