"""Explicit diagnostic tasks; expected answers never enter candidate checkouts."""

from dataclasses import dataclass
import json
from pathlib import Path

from fixture_cases import CASES as CSV_CASES
from structured_cases import GRAPH_CASES, CONFIG_CASES

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(frozen=True)
class Fixture:
    name: str
    module: str
    function: str
    cases: list

    @property
    def root(self):
        return ROOT / self.name

    def arguments(self, value):
        return (
            [value["base"], value["override"]]
            if self.name == "config-merge-v1"
            else [value]
        )

    def input_bytes(self, value):
        text = value if self.name == "csv-summary-v1" else json.dumps(value)
        return text.encode("utf-8")


FIXTURES = {
    "csv-summary-v1": Fixture("csv-summary-v1", "csv_summary", "summarize", CSV_CASES),
    "dependency-order-v1": Fixture(
        "dependency-order-v1", "dependency_order", "order_tasks", GRAPH_CASES
    ),
    "config-merge-v1": Fixture(
        "config-merge-v1", "config_merge", "merge_config", CONFIG_CASES
    ),
}


def fixture(name):
    try:
        return FIXTURES[name]
    except KeyError:
        raise ValueError("unknown fixture") from None
