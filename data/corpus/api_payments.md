# Payments API Reference

The Payments API lets you create and query card payments.

## Authentication
All requests require a Bearer token in the `Authorization` header. Tokens are issued per
merchant and must be kept secret. Example: `Authorization: Bearer <token>`.

## Create a payment
`POST /v1/payments`

Required fields: `amount` (minor units, integer), `currency` (ISO 4217), `card_token`,
and `merchant_reference`. To make retries safe, send an `Idempotency-Key` header with a
unique value per logical payment. Re-sending the same key returns the original result
instead of charging the customer twice.

### Response statuses
- `authorized` — funds held, not yet captured.
- `captured` — funds captured; money will settle.
- `declined` — issuer rejected the payment (see the `error_code` field).
- `failed` — a technical error occurred (gateway/network); safe to retry with the same
  `Idempotency-Key`.

## Query a payment
`GET /v1/payments/{id}` returns the current status and, if declined, the `error_code` and
`decline_reason`.
