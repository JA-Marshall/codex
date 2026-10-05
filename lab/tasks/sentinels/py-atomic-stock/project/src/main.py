import json
import sys
from app import run

try:
    print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
except (ValueError, KeyError, TypeError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(2)
