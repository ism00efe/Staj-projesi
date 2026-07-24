# Captures API Reference

`POST /v1/captures` — capture a previously authorized payment.

## Usage
Requires `payment_id`. Only `authorized` payments can be captured, and only once.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
