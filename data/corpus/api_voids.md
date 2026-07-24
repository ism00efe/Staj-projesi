# Voids API Reference

`POST /v1/voids` — release an authorization without capturing.

## Usage
Voids apply to `authorized` payments; a captured payment must be refunded instead.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
