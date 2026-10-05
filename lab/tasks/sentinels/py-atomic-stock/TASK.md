# Add atomic stock batches to the existing CLI

Keep the existing JSON request/response wire format and single `adjust` command. Add `batch`, carrying `changes: [{sku, delta}, ...]`, to the ordered command list.

- R-atomic: a failed batch changes no stock. Later commands see the last successfully committed stock.
- R-net: sum repeated SKU deltas, then validate final stock is nonnegative; intermediate negative totals within a batch are allowed. An empty batch succeeds.
- R-compat: preserve existing adjust behavior and result objects. Every successful command appends `{ok: true}`; failures append `{error: CODE}` and processing continues. Codes are `unknown-sku`, `invalid-delta`, `negative-stock`, and `unsupported-op`. Deltas must be integers, excluding booleans.

Input: `{stock: {SKU: quantity}, commands: [...]}`. Output: `{stock, results}`. `adjust` carries `sku` and `delta`. Starting stock is valid and nonnegative. Modify only src/ and tests/.
