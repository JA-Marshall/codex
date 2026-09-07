import json
from pathlib import Path
import sys

from dependency_order import order_tasks


def main():
    if len(sys.argv) != 2:
        return 2
    try:
        graph = json.loads(Path(sys.argv[1]).read_bytes().decode("utf-8"))
        output = json.dumps(order_tasks(graph)) + "\n"
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
