import json
from pathlib import Path
from tokenizer import counts

def build(root_name, index_name):
    root = Path(root_name)
    target = Path(index_name)
    documents = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix == ".txt" and path.resolve() != target.resolve():
            documents[path.relative_to(root).as_posix()] = counts(path.read_text(encoding="utf-8"))
    payload = {"version": 1, "documents": documents}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8", newline="\n")
    terms = set()
    for words in documents.values():
        terms.update(words)
    return {"documents": len(documents), "terms": len(terms)}

def query(index_name, text):
    payload = json.loads(Path(index_name).read_text(encoding="utf-8"))
    terms = set(counts(text))
    matches = []
    if terms:
        for path, words in payload["documents"].items():
            if terms & words.keys():
                matches.append({"path": path, "score": sum(words[term] for term in terms)})
    matches.sort(key=lambda result: (-result["score"], result["path"]))
    return matches
