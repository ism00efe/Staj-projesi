# Tokens API Reference

`POST /v1/tokens` — exchange raw card details for a reusable token.

## Usage
Raw PAN never touches merchant servers; tokens are scoped per merchant.

## Idempotency
Send an `Idempotency-Key` header on every write request so a retry never duplicates the operation.

## Errors
Validation failures return 4xx with an `error_code`; upstream failures return `PAY-6006 gateway_timeout` and are safe to retry.
