# Settlement Inquiry API Reference

`GET /v1/settlements/{batch_id}` — query the status of a settlement (takas) batch.

## Usage
Returns per-transaction reconciliation status against the acquirer file. See `concept_pos_atm_flow.md` for how authorization, capture, and settlement relate.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
