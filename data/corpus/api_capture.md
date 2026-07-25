# Capture API Reference

`POST /v1/captures` — capture (settle) a previously authorized transaction.

## Usage
Requires `authorization_id`. Only transactions in `authorized` state can be captured, and only once — a second capture returns RC-12 (`Invalid Transaction`).

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
