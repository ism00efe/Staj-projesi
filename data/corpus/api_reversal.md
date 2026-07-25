# Reversal API Reference

`POST /v1/reversals` — reverse (void) an authorization before it settles, equivalent to an ISO 8583 MTI 0420 request.

## Usage
Requires the original `stan` and `rrn`. A reversal releases the held funds without a capture; once a transaction has settled, use `api_refund.md` instead.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
