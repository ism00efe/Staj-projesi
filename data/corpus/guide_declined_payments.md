# Troubleshooting Guide: Declined Payments

When a payment is `declined`, read the `error_code` first — it determines whether a retry
can ever succeed.

## Decision flow
- `insufficient_funds` (PAY-1001) / `do_not_honor` (PAY-4004): issuer decline. Retrying
  the same card will not help; ask for another payment method.
- `invalid_card` (PAY-2002) / `expired_card` (PAY-3003): validation. Ask the customer to
  correct the card details.
- `3ds_authentication_failed` (PAY-5005): authentication. Retry the 3DS challenge once;
  if it fails again, escalate to runbook_3ds_failures.
- `fraud_suspected` (PAY-9009): do not retry; route to manual risk review.

## Anti-patterns
- Never auto-retry issuer declines in a loop — it can trigger issuer velocity blocks.
- Never retry without an `Idempotency-Key`.
