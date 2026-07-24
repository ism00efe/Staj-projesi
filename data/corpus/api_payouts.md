# Payouts API Reference

`POST /v1/payouts` — send funds to a connected account.

## Usage
Requires `destination` and `amount`. Payouts settle on the next banking cycle.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
