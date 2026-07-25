# Refund API Reference

`POST /v1/refunds` — refund a captured (settled) transaction.

## Usage
Requires `transaction_id` and `amount`. Partial refunds are allowed up to the captured total. Refund settlement follows the standard takas (clearing) cycle, typically 1-3 business days.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
