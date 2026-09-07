import json
from pathlib import Path
import sys

from config_merge import merge_config


def main():
    if len(sys.argv) != 2:
        return 2
    try:
        data = json.loads(Path(sys.argv[1]).read_bytes().decode("utf-8"))
        if not isinstance(data, dict) or set(data) != {"base", "override"}:
            raise ValueError("expected base and override")
        output = (
            json.dumps(merge_config(data["base"], data["override"]), sort_keys=True)
            + "\n"
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
