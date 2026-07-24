# Disputes API Reference

`GET /v1/disputes` — list chargebacks raised against payments.

## Usage
Each dispute carries a `reason_code` and an evidence submission deadline.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
