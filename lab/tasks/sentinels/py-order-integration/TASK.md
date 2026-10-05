Implement order reservation across the existing app, orders, and report modules.
Input JSON has state {stock: {sku: available_count}, orders: {id: order}} and an
ordered operations list. A reserve operation has op, id, sku, and quantity.
Quantity must be a positive integer (not bool), ID must be new, and sufficient
stock must exist. Success deducts stock and records {sku, quantity, status:"reserved"}.
Output state, ordered results, and summary {available, reserved}; summary maps every
stock SKU to its available count and active reserved quantity. Retain all orders.

Each result is "ok", "invalid-order" (duplicate ID or invalid quantity),
"unavailable" (missing SKU or insufficient stock), or "unsupported-operation".
Failures leave state unchanged and later operations continue. Preserve input state.
Submit the initial implementation; a follow-up will arrive after verified delivery.
