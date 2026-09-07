# Build a word-frequency CLI

Implement the supplied word-frequency scaffold. `LIMIT` is a nonnegative ASCII decimal integer;
invalid arguments return `usage: LIMIT`. Read all text from stdin and Unicode-casefold it before
tokenization. A word consists of Unicode alphanumeric characters (no underscores), optionally
joined by single ASCII apostrophes that have alphanumeric characters on both sides. Other
characters separate words. Thus `can't` stays one word, `x_y` is two, and `a''b` is two.

Return `{"total":N,"unique":U,"top":[{"word":W,"count":C},...]}`. Rank by descending
count, then ascending casefolded word using Python string order. Limit only the top array;
counts describe the entire input. Zero, empty input, digits, and non-ASCII text are supported.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
