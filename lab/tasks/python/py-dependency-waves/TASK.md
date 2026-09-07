# Build dependency-wave planning

Implement a build planner with no command arguments. Stdin is a JSON object mapping task names
to lists of prerequisite names. Return `{"waves":[[...],...],"tasks":N}`: each wave contains,
in ascending string order, every remaining task whose prerequisites were completed in earlier
waves. Tasks becoming ready during a wave wait for the next wave. Repeated prerequisites
count once; input key order must not affect output. Empty input produces zero waves.

Reject non-object inputs, non-list values, and non-string prerequisites with `invalid graph`.
Reject referenced names absent from the object with `unknown dependency: NAME`, choosing the
lexicographically smallest missing name. Validate missing names before cycle detection.
Any directed cycle, including a self-edge or a cycle in only one component, returns `cycle`.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
