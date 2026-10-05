import json
import sys
from app import run

print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
