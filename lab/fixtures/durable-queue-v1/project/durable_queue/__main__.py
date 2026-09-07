import argparse
import json

from .queue import Queue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    with open(args.request, encoding="utf-8") as stream:
        request = json.load(stream)
    operation = request.pop("op")
    value = getattr(Queue(args.db), operation)(**request)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
