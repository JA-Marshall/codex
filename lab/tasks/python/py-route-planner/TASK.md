# Repair cheapest-route selection and canonical ties

Route results sometimes prefer an expensive direct connection over a cheaper connection through
another node. Repair the planner while retaining validated graph loading, batch queries, and
deterministic output. CLI argument GRAPH names a JSON file with exactly `nodes` (unique nonempty
string names) and `edges` (a list). Edges contain exactly `from`, `to`, and `cost`, referring to
existing nodes, with a positive integer cost excluding booleans. Edges are directed. Parallel
edges and positive self-edges are allowed. Invalid container/node schemas return `invalid graph`;
malformed edges, unknown endpoints, and nonpositive costs return `invalid edge`.

Stdin is an array of two-string `[start,end]` queries. Validate every query before computing output.
Invalid query shapes return `invalid queries`; unknown names return `unknown node`. Return one
`{"cost":N,"path":[names...]}` object per query, preserving query order. Minimize total edge cost.
Tied costs use the lexicographically smallest *entire node-name sequence*, using Python string
and tuple order. Input edge/node order must not affect results. Self queries cost zero and have
a one-node path. Unreachable destinations return `{"cost":null,"path":[]}`. Inputs contain at
most 100 nodes/1000 edges; use a graph search rather than enumerating all possible paths.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
