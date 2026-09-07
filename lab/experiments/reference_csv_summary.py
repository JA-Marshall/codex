"""Evaluator calibration reference; never included in the candidate checkout."""

import csv
import io


def summarize(text: str) -> dict[str, int]:
    text = text.removeprefix("\ufeff")
    state = "start"
    for character in text:
        if state == "quoted":
            if character == '"':
                state = "closed"
        elif state == "closed":
            if character == '"':
                state = "quoted"
            elif character in ",\r\n":
                state = "start"
            else:
                raise ValueError("characters after closing quote")
        elif character == '"':
            if state != "start":
                raise ValueError("quote in unquoted field")
            state = "quoted"
        elif character in ",\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise ValueError("unterminated quote")
    try:
        rows = (row for row in csv.reader(io.StringIO(text, newline=""), strict=True) if row)
        header = next(rows, None)
        if header is None:
            return {}
        if header != ["category", "count"]:
            raise ValueError("expected category,count header")
        totals = {}
        for row in rows:
            if len(row) != 2 or not row[1] or not all("0" <= char <= "9" for char in row[1]):
                raise ValueError("invalid count record")
            category, count = row
            totals[category] = totals.get(category, 0) + int(count)
        return totals
    except csv.Error as error:
        raise ValueError(str(error)) from error
