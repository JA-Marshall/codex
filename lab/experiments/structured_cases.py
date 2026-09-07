"""Host-only expected answers for algorithm and configuration tasks."""

GRAPH_CASES = [
    ("empty", {}, []),
    ("independent", {"z": [], "a": [], "m": []}, ["a", "m", "z"]),
    ("dependency", {"build": ["setup"], "setup": []}, ["setup", "build"]),
    ("newly-ready", {"b": ["a"], "a": [], "z": []}, ["a", "b", "z"]),
    ("diamond", {"d": ["b", "c"], "c": ["a"], "b": ["a"], "a": []}, ["a", "b", "c", "d"]),
    ("duplicate-edge", {"a": ["b", "b"], "b": []}, ["b", "a"]),
    ("cycle", {"a": ["b"], "b": ["a"]}, None),
    ("self-cycle", {"a": ["a"]}, None),
    ("disconnected-cycle", {"ok": [], "a": ["b"], "b": ["a"]}, None),
    ("missing-node", {"a": ["missing"]}, None),
    ("bad-root", [], None),
    ("bad-dependencies", {"a": "b", "b": []}, None),
    ("bad-dependency-item", {"a": [1]}, None),
    ("empty-name", {"": []}, None),
]

CONFIG_CASES = [
    ("empty", {"base": {}, "override": {}}, {}),
    ("preserve", {"base": {"a": 1}, "override": {}}, {"a": 1}),
    ("add", {"base": {"a": 1}, "override": {"b": 2}}, {"a": 1, "b": 2}),
    ("recursive", {"base": {"db": {"host": "local", "port": 80}}, "override": {"db": {"port": 90}}}, {"db": {"host": "local", "port": 90}}),
    ("deep", {"base": {"a": {"b": {"x": 1, "y": 2}}}, "override": {"a": {"b": {"x": 3}}}}, {"a": {"b": {"x": 3, "y": 2}}}),
    ("replace-list", {"base": {"a": [1, 2]}, "override": {"a": [3]}}, {"a": [3]}),
    ("empty-list", {"base": {"a": [1]}, "override": {"a": []}}, {"a": []}),
    ("explicit-null", {"base": {"a": 1}, "override": {"a": None}}, {"a": None}),
    ("false-zero", {"base": {"a": True, "b": 5}, "override": {"a": False, "b": 0}}, {"a": False, "b": 0}),
    ("object-to-scalar", {"base": {"a": {"b": 1}}, "override": {"a": "new"}}, {"a": "new"}),
    ("scalar-to-object", {"base": {"a": 1}, "override": {"a": {"b": 2}}}, {"a": {"b": 2}}),
    ("empty-overlay-object", {"base": {"a": {"b": 1}}, "override": {"a": {}}}, {"a": {"b": 1}}),
    ("bad-base", {"base": [], "override": {}}, None),
    ("bad-overlay", {"base": {}, "override": None}, None),
]
