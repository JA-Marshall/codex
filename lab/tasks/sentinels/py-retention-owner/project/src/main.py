import json
import sys
from app import run

print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
