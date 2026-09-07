"""Validate the queue contract's JSON output without prescribing its escaping style."""

import json
import math


def parse_cli_output(data):
    """Accept one UTF-8 JSON value, sorted object keys, and one final newline."""
    text = data.decode("utf-8")
    trailing = text[len(text.rstrip(" \t\r\n")) :]
    if not text.endswith("\n") or trailing.count("\n") != 1:
        raise ValueError("one final newline required")

    def ordered(pairs):
        keys = [key for key, _ in pairs]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("object keys must be unique and sorted")
        return dict(pairs)

    def constant(value):
        raise ValueError("non-JSON constant")

    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite JSON value")
        return result

    return json.loads(
        text, object_pairs_hook=ordered, parse_constant=constant, parse_float=finite
    )
