# Implementation plan

This is a projection of the canonical plan; it does not grant approval.

Text values use JSON string notation inside code spans to preserve exact content.

- Schema version: 1
- Plan ID: `"task-plan"`
- Revision: 1

## Goal

`"Fix layered-config API and CLI to meet merge contract while preserving entry points, with focused regression tests."`

## Assumptions

- `"Python 3.12 stdlib-only implementation; keep change small."`
- `"Preserve entry points config_merge.merge_config and cli.main."`
- `"Inputs are JSON-compatible values with string keys."`

## Implementation steps

### Step `"S1"`

- ID: `"S1"`
- Title: `"Fix config_merge.py pure recursive merge"`
- Instructions: `"Rewrite merge_config: if not isinstance(base,dict) or not isinstance(override,dict) raise ValueError; return new dict copying base deep-ish via recursion, recursing only when both values are dict else deep-copying override value."`

**Affected files**

- `"config_merge.py"`

**Dependencies**

_None._

**Acceptance criteria**

- `"AC1"`
- `"AC2"`
- `"AC3"`

**Verification**

- `"V1"`

### Step `"S2"`

- ID: `"S2"`
- Title: `"Audit/harden cli.py error handling"`
- Instructions: `"Audit cli.py, preserve main() signature; ensure no stdout write on error path and invalid base/override or JSON/UTF-8/usage maps to return 2 with empty stdout; widen except to include TypeError only if needed."`

**Affected files**

- `"cli.py"`

**Dependencies**

- `"S1"`

**Acceptance criteria**

- `"AC4"`

**Verification**

- `"V1"`
- `"V2"`

### Step `"S3"`

- ID: `"S3"`
- Title: `"Add focused regression tests"`
- Instructions: `"Add tests/test_regression.py covering dict-vs-scalar both ways, list replace, None/False/0 replace, empty-overlay preserves, deep no-mutate, non-dict roots ValueError, CLI happy-path sorted+newline and CLI failures (bad args, missing/extra field, bad JSON) asserting exit 2 and empty stdout."`

**Affected files**

- `"tests/test_regression.py"`

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

## Risks

- `"Shallow/deep copy hiding nested mutation; build new dict recursively."`
- `"Use isinstance(x,dict); ensure dict-vs-scalar both directions replace."`
- `"CLI must not write partial stdout; validate before write and map all input/emit errors to exit 2."`
- `"JSONDecodeError/UnicodeDecodeError are ValueError subclasses; also guard TypeError on bad roots."`

## Acceptance criteria

- `"AC1"`: `"Recursive dict-dict merge only; otherwise replace; missing keys preserved."`
- `"AC2"`: `"Lists replace; None/False/0 replace; empty dict overlay preserves base keys."`
- `"AC3"`: `"No mutation of inputs incl. nested; non-dict roots raise ValueError."`
- `"AC4"`: `"CLI prints sorted-keys JSON plus exactly one newline; all invalid input/usage exits 2 with empty stdout; entry points preserved."`

## Verification strategy

- `"V1"`: `"Run full suite: python3.12 -m unittest discover -s tests -v"`
- `"V2"`: `"CLI smoke: python3.12 cli.py valid.json (check sorted keys + single newline, exit 0) and python3.12 cli.py bad.json / missing arg (check exit 2 and empty stdout)."`

## Discoveries

- `"config_merge.py merge_config uses base.update(override): shallow, mutates base, no recursion/validation."`
- `"cli.py main() takes 1 UTF-8 JSON file, checks set(data)=={base,override}, dumps sort_keys+newline, except OSError,ValueError returns 2."`
- `"tests/test_public.py has 3 tests: empty, nested-preserve, shallow no-mutation."`
- `"TASK.md contract requires deep pure merge, list-replace, None/False/0 handling, ValueError on non-object roots."`

## Blockers

_None._
