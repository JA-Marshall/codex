# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Fix CSV summary API and CLI per contract, preserve entry points, add focused public regression tests"`

## Assumptions

- `"Python 3.12 stdlib only (csv, json, re)"`
- `"Preserve summarize(text:str)-\u003edict[str,int] and python3.12 cli.py INPUT.csv entry points"`
- `"Empty input and header-without-data return {}"`
- `"Preserve category text verbatim; no implementation until human approval"`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Rewrite summarize to strict CSV contract"`
- Instructions: `"Rewrite summarize using csv.reader(strict=True) over text split with BOM strip, exact header category,count check, skip empty records, enforce 2 fields per record, validate count with ^[0-9]+$ then int, sum by verbatim category, ValueError otherwise."`

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
- Title: `"Harden CLI atomic output and exit codes"`
- Instructions: `"Harden cli.py: read UTF-8 file, call summarize, build json.dumps(sort_keys=True)+newline string first then single print, catch OSError/ValueError to stderr with exit 2 and no stdout."`

**Affected files**

- `"cli.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC3"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Add focused regression tests"`
- Instructions: `"Add tests/test_regression.py covering BOM, CRLF, quoted comma/escaped quote, empty/header-only/empty-record, repeated sum, and each ValueError class plus CLI success/failure stdout/exit checks."`

**Affected files**

- `"tests/test_regression.py"`

**Dependencies**

- `"S1"`
- `"S2"`

**Acceptance criteria**

- `"AC1"`
- `"AC2"`
- `"AC3"`

**Verification**

- `"V1"`

### Step `"S4"`

- ID: `"S4"`
- Title: `"Run verification suite"`
- Instructions: `"Run full verification, report results, make no code changes in this step."`

**Affected files**

_None._

**Dependencies**

- `"S3"`

**Acceptance criteria**

- `"AC4"`

**Verification**

- `"V1"`
- `"V2"`

## Risks

- `"csv.reader strict mode plus utf-8-sig BOM handling and empty-record skip must be exact"`
- `"Count validation must use ASCII regex ^[0-9]+$ not int()"`
- `"CLI must buffer output for atomic stdout with exact sorted JSON plus newline"`

## Acceptance criteria

- `"AC1"`: `"summarize returns correct dict for empty, header-only, CRLF, BOM, quoted commas/escaped quotes, empty records, verbatim categories, summed repeats"`
- `"AC2"`: `"summarize raises ValueError for bad header, malformed quoting, stray quotes, wrong field count, negative/whitespace/non-ASCII/non-digit counts"`
- `"AC3"`: `"CLI prints sorted-keys JSON plus single newline on success, exits 2 with empty stdout on invalid input/usage error"`
- `"AC4"`: `"python3.12 -m unittest discover -s tests -v passes including new regression tests"`

## Verification strategy

- `"V1"`: `"Run python3.12 -m unittest discover -s tests -v and require all tests pass"`
- `"V2"`: `"Run python3.12 cli.py INPUT.csv on valid file checking sorted JSON plus newline, and on invalid file checking exit 2 with empty stdout"`

## Discoveries

- `"csv_summary.py:4-13 splitlines+split(',')+int() breaks quoted commas/escaped quotes, ignores CRLF/BOM, int() allows whitespace/+/unicode digits"`

## Blockers

_None._
