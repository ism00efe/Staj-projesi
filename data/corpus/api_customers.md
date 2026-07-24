# Customers API Reference

`POST /v1/customers` — store a customer profile for repeat payments.

## Usage
Customers may hold multiple saved card tokens; deletion is irreversible.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
