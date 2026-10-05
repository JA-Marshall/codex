# Reversible inventory archival

Add archive and restore actions to the existing JSON CLI. Archiving removes an item from the default visible list, while keeping the complete record and its audit history so it can be restored. This is a visibility change with reversible state.

- R-archive: preserve item IDs, order, metadata, and all prior audit events.
- R-history: append `archived` or `restored` exactly when active state changes. Repeating an action must be idempotent.
- R-compat: requests without actions retain the existing list behavior. Unknown IDs and unsupported actions fail with exit 2 and an explanatory stderr message.

Input contains `items` and optional ordered `actions`, each with `op` (`archive` or `restore`) and `id`. Output is `{items, visible}`, where `visible` lists active IDs in original item order. Existing IDs are opaque strings. Modify only src/ and tests/; keep the CLI wire format.

Run `python -m unittest discover -s tests` for the visible check.
