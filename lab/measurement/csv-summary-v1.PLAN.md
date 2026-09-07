# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Fix CSV summary API and CLI per contract while preserving entry points and add focused public regression tests."`

## Assumptions

- `"Empty string means empty input -\u003e {}."`
- `"Header is parsed as CSV and must equal [\"category\",\"count\"] exactly."`
- `"Blank CSV records ([]) are empty records and skipped."`
- `"Only Python 3.12 standard library; keep csv_summary.summarize and cli.main entry points."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Rewrite summarize with strict CSV validation"`
- Instructions: `"Rewrite summarize(text:str)-\u003edict in csv_summary.py using io.StringIO+csv.reader(strict=True): strip one leading \\ufeff, return {} if text==\"\", require header==[\"category\",\"count\"] else ValueError, skip [] rows, require len==2 else ValueError, require re ^[0-9]+$ on counts then int() and sum by preserved category, normalize csv.Error to ValueError."`

**Affected files**

- `"csv_summary.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`
- `"AC2"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Confirm CLI atomic sorted JSON output"`
- Instructions: ``"Audit cli.py main()-\u003eint keeping signature and `python cli.py INPUT.csv`: read_text utf-8, call summarize, build json.dumps(sort_keys=True)+\"\\n\" string then single write/print so invalid exits 2 with empty stdout; only edit if buffering or passthrough needs fix."``

**Affected files**

- `"cli.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC3"`

**Verification**

- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Add focused public regression tests"`
- Instructions: `"Add focused tests in tests/test_public.py: BOM/CRLF/escaped-quotes/empty/header-only/sum-repeats, rejects for bad header/field-count/malformed quotes/whitespace/negative/non-ASCII counts, CLI success newline+sorted keys and CLI failure exit 2 empty stdout."`

**Affected files**

- `"tests/test_public.py"`

**Dependencies**

- `"S1"`
- `"S2"`

**Acceptance criteria**

- `"AC1"`
- `"AC2"`
- `"AC3"`
- `"AC4"`

**Verification**

- `"V1"`
- `"V2"`
- `"V3"`

## Risks

- `"Multiline quoted fields and lone \\r mishandled if not using csv.reader."`
- `"int() accepts whitespace/underscore/unicode digits so regex gate is required."`
- `"Whitespace-only lines vs empty records."`
- `"CLI partial stdout if printing before full validation."`

## Acceptance criteria

- `"AC1"`: `"summarize returns correct sums for empty, header-only, BOM, CRLF, quoted commas/escaped quotes, skipped empty records, preserved categories"`
- `"AC2"`: `"summarize raises ValueError for bad header, malformed quoting, wrong field count, and non-^[0-9]+$ counts (whitespace, negative, non-ASCII)"`
- `"AC3"`: `"CLI with one UTF-8 file prints sorted-keys JSON plus one newline; invalid/usage exits 2 with empty stdout"`
- `"AC4"`: `"python3.12 -m unittest discover -s tests -v is green; entry points and stdlib-only small implementation preserved"`

## Verification strategy

- `"V1"`: `"API matrix: run python3.12 -m unittest discover -s tests -v covering valid and ValueError cases"`
- `"V2"`: `"CLI checks: run python3.12 -m unittest discover -s tests -v including subprocess CLI success/failure (exit 2 empty stdout) tests"`
- `"V3"`: `"Full suite: run python3.12 -m unittest discover -s tests -v and confirm green"`

## Discoveries

- `"csv_summary.py summarize uses splitlines+split(',')+int(): breaks quoted commas/escaped quotes, multiline CRLF fields, BOM header, strict count checks, field-count/quote errors."`
- ``"cli.py main()-\u003eint for `python cli.py INPUT.csv` reads UTF-8, calls summarize, print(json.dumps(sort_keys=True)): usage/invalid-\u003e2+stderr shape correct but inherits API bugs; must buffer output to avoid partial stdout."``
- `"tests/test_public.py has 3 tests (repeat-sum, quoted-comma, CLI sorted JSON); missing BOM/CRLF/strict-count/invalid-input coverage."`
- `"Contract requires csv.reader semantics with strict=True, leading BOM strip, ^[0-9]+$ counts, quotes only as delimiters/escaped quotes."`

## Blockers

_None._
