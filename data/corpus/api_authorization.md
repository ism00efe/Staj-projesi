# Authorization API Reference

`POST /v1/authorizations` — submit an ISO 8583-style authorization request (equivalent to an MTI 0100).

## Usage
Fields mirror ISO 8583 data elements: `pan` (DE2, tokenized), `processing_code` (DE3), `amount` (DE4), `stan` (DE11, caller-generated), `merchant_id` (DE42), `terminal_id` (DE41). The response includes `response_code` (DE39) — see `errorcodes_iso8583.md` for the full code table.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
