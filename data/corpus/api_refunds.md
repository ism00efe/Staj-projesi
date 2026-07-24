# Refunds API Reference

## Create a refund
`POST /v1/refunds`

Required fields: `payment_id`, `amount` (minor units). Partial refunds are allowed as long
as the cumulative refunded amount does not exceed the captured amount. Refunds are also
idempotent via the `Idempotency-Key` header.

## Rules
- A payment must be in `captured` state before it can be refunded.
- Refunds against `authorized`-only payments must first be voided, not refunded.
- Refund settlement can take 1-5 business days depending on the issuer.

## Common failures
- `refund_exceeds_captured` — requested amount is larger than what remains refundable.
- `payment_not_captured` — the payment has not been captured yet.
