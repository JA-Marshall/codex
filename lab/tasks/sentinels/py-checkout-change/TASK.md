Implement checkout totals in src/app.py. The JSON input has items, each with
sku, category, nonnegative integer unit_price in cents, and positive integer
quantity. Return subtotal, shipping, and total integer fields. Charge 500 cents
shipping when subtotal is below 5000; otherwise shipping is free, including the
exact 5000 boundary. Empty orders follow the same rule. Preserve the CLI.

Submit a runnable implementation of this initial request. A follow-up request
will be supplied after the host observes a working initial checkout. Preserve
existing behavior while implementing the follow-up; do not invent it in advance.
