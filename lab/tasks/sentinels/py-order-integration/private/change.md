Add cancel operations with op:"cancel" and id. Cancelling an active reservation
returns its quantity to available stock and sets its order status to "cancelled".
Retain the order record. Repeated cancellation succeeds without additional stock
changes. Cancelling an unknown ID returns "unknown-order" without state changes.
Cancelled orders no longer contribute to summary.reserved. Subsequent reserve
operations must immediately see released stock; all original reserve validation,
error isolation, output fields, and order history obligations remain in force.
