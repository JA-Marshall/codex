import json
import sys
from app import run

try:
    sys.stdout.write(run(json.load(sys.stdin)))
except (ValueError, KeyError, TypeError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(2)
