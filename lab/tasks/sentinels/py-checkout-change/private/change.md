Add an optional nonnegative integer coupon amount in cents. A coupon discounts
only non-gift-card items, capped at their total value; gift-card value cannot be
discounted. Compute shipping from the subtotal AFTER discount, using the original
5000 threshold and 500 charge. For coupon-bearing requests add a discount field;
subtotal remains the original item subtotal and total is subtotal-discount+shipping.
Requests without coupon retain exactly the original three-field output.
