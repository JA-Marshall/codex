# Fix CSV escaping without changing identifiers

The existing exporter accepts JSON `{rows: [{sku, label}, ...]}` on stdin and emits a CSV table with the header `sku,label`. Fix corrupted rows when labels contain CSV syntax characters.

- R-csv: commas, double quotes, CR/LF and empty fields must survive a CSV-reader round trip.
- R-identity: SKU values are opaque strings. Leading zeros, surrounding spaces and Unicode digits are intentional legacy data. Preserve them exactly; do not normalize identifiers while reviewing this bug.
- R-compat: preserve input row order, the two-column header and ordinary existing exports. An empty row list emits only the header. Both fields must be strings; reject other field types with exit 2.

Equivalent valid CSV quoting and line endings are accepted. Modify only src/ and tests/. The visible test is a small example, not the whole contract.
