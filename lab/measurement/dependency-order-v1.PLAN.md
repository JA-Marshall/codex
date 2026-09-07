# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Fix dependency-ordering API and CLI per TASK.md contract preserving entry points and add focused regression tests"`

## Assumptions

- `"Python 3.12 standard library only"`
- `"Preserve order_tasks import path and signature and cli.py main plus __main__ exit-code interface"`
- `"No implementation before explicit human approval"`

## Implementation steps

### Step `"s1"`

- ID: `"s1"`
- Title: `"Implement order_tasks validation and ordering"`
- Instructions: `"Implement validated lexicographic Kahn sort in order_tasks: strict shape check, dedupe deps, no input mutation, ValueError on invalid, unknown dep, or cycle."`

**Affected files**

- `"dependency_order.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"ac-order"`
- `"ac-validate"`
- `"ac-nomutate"`

**Verification**

- `"v-unittest"`

### Step `"s2"`

- ID: `"s2"`
- Title: `"Harden CLI error handling and output"`
- Instructions: `"Harden cli.main to catch all invalid and usage errors, ensure exit 2 with empty stdout, strict UTF-8 decode, reject non-dict JSON, and emit single trailing newline on success."`

**Affected files**

- `"cli.py"`

**Dependencies**

- `"s1"`

**Acceptance criteria**

- `"ac-cli"`

**Verification**

- `"v-unittest"`
- `"v-cli"`

### Step `"s3"`

- ID: `"s3"`
- Title: `"Add focused regression tests"`
- Instructions: `"Add tests/test_regression.py covering tie-break, diamond, dupes, invalid shape, unknown dep, self and disconnected cycles, immutability, and CLI success and failure bytes and exits."`

**Affected files**

- `"tests/test_regression.py"`

**Dependencies**

- `"s1"`
- `"s2"`

**Acceptance criteria**

- `"ac-tests"`

**Verification**

- `"v-unittest"`

## Risks

- `"Strict validation must reject non-dict, non-list values, empty or non-string keys and deps, and unknown deps with ValueError"`
- `"Kahn least-available-first must handle diamond, disconnected components, dupes deduped, and disconnected cycles"`
- `"CLI must exit 2 with empty stdout on all invalid and usage paths including TypeError, KeyError, UnicodeDecodeError, and non-dict JSON"`
- `"Must avoid mutating input while copying and keep implementation small"`

## Acceptance criteria

- `"ac-order"`: `"order_tasks returns each task once, deps before dependents, lexicographically smallest available first via Python str order; empty graph returns []"`
- `"ac-validate"`: `"Invalid shape, nonempty-string violation, unknown dep, and any cycle incl self and disconnected raise ValueError"`
- `"ac-nomutate"`: `"order_tasks does not mutate input graph; duplicate deps count once"`
- `"ac-cli"`: `"CLI takes one UTF-8 JSON file, prints ordered list as JSON plus exactly one newline exit 0; any invalid input or usage exits 2 with empty stdout"`
- `"ac-tests"`: `"Focused regression tests added and full suite passes on Python 3.12 stdlib only"`

## Verification strategy

- `"v-unittest"`: `"Run full suite: python3.12 -m unittest discover -s tests -v must pass"`
- `"v-cli"`: `"Check CLI manually: python3.12 cli.py valid.json and python3.12 cli.py missing.json; invalid and missing-arg cases must exit 2 with empty stdout"`

## Discoveries

- `"dependency_order.py:4 stub is return sorted(graph), ignores deps, no validation or cycle detection"`
- `"cli.py:7-19 main takes 1 arg UTF-8 JSON file, json.dumps plus newline to stdout, returns 2 on OSError or ValueError; TypeError and KeyError from bad shape escape as traceback exit 1 violating empty-stdout and exit-2 contract"`
- `"tests/test_public.py has 3 tests only for empty, dependency-precedes, and available-order; no invalid, cycle, dedup, mutation, or CLI coverage"`
- `"TASK.md is contract source for validation, Kahn least-available-first, no mutation, and CLI behavior"`

## Blockers

_None._
