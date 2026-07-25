# Recurring Billing API Reference

`POST /v1/subscriptions` — charge a tokenized card on a recurring schedule.

## Usage
Recurring (merchant-initiated) transactions are generally exempt from a fresh 3DS challenge under card-scheme rules, provided the initial charge was customer-initiated and challenged.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
