import hashlib
from pathlib import Path

def check(root, entry):
    path = Path(root) / entry["path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"id": entry["id"], "status": "ok" if digest == entry["sha256"] else "mismatch", "actual": digest}
