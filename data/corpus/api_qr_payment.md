# Qr Payment API Reference

`POST /v1/qr-payments` — generate or redeem a QR code payment.

## Usage
Static or dynamic QR codes encode a `merchant_id` and optional fixed `amount`; redemption follows the same authorization path as a card-present transaction.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
