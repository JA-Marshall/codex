import json
import sys
from app import run

if __name__ == "__main__":
    try:
        result = run(sys.argv[1:], sys.stdin.read())
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
