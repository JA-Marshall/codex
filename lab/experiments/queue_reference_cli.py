"""Private CLI reference used only by offline evaluator validation."""
import argparse
import inspect
import json
import sqlite3

from .queue import Queue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        with open(args.request, encoding="utf-8") as stream:
            request = json.load(stream)
        if not isinstance(request, dict):
            raise ValueError("object required")
        op = request.pop("op", None)
        if op not in ("submit", "get", "list", "claim", "recover", "complete", "fail"):
            raise ValueError("unknown operation")
        method = getattr(Queue(args.db), op)
        inspect.signature(method).bind(**request)
        result = method(**request)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, sqlite3.Error):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
