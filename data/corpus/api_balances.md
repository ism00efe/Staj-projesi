# Balances API Reference

`GET /v1/balances` — read available and pending balances.

## Usage
Pending funds become available after the settlement window closes.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
