import json
from pathlib import Path
from manifest import validate
from verifier import verify

def run(argv, stdin):
    if len(argv) != 3:
        raise ValueError("usage: ROOT MANIFEST REPORT")
    root, manifest_name, report = argv
    entries = validate(json.loads(Path(manifest_name).read_text(encoding="utf-8")))
    results = verify(root, entries)
    summary = {"ok": sum(item["status"] == "ok" for item in results),
               "mismatch": sum(item["status"] == "mismatch" for item in results),
               "error": sum(item["status"] == "error" for item in results)}
    payload = {"results": results, "summary": summary}
    Path(report).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="utf-8", newline="\n")
    return summary
