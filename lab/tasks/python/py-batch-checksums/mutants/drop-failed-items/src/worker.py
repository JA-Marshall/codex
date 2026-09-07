import hashlib
from pathlib import Path, PurePosixPath

def check(root, entry):
    relative = entry["path"]
    parts = relative.split("/")
    if ("\\" in relative or ":" in relative or relative.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)):
        return {"id": entry["id"], "status": "error", "error": "unsafe path"}
    path = Path(root).joinpath(*parts)
    try:
        if not path.is_file():
            return {"id": entry["id"], "status": "error", "error": "not a file"}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return {"id": entry["id"], "status": "error", "error": "unreadable file"}
    return {"id": entry["id"], "status": "ok" if digest == entry["sha256"] else "mismatch", "actual": digest}
