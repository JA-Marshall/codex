"""Print category totals for one CSV file."""

import json
import sys
from pathlib import Path

from csv_summary import summarize


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: cli.py INPUT.csv", file=sys.stderr)
        return 2
    try:
        result = summarize(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
