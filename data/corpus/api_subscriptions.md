# Subscriptions API Reference

`POST /v1/subscriptions` — bill a customer on a recurring schedule.

## Usage
Recurring charges are exempt from 3DS where regulation allows a MIT exemption.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
