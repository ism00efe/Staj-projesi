# Openbanking Payment API Reference

`POST /v1/openbanking/payment-orders` — initiate an open banking payment order (ödeme emri) on behalf of a customer.

## Usage
Requires explicit customer consent (`consent_id`) obtained via the open banking consent flow. See `errorcodes_openbanking.md` for consent- and IBAN-related failures.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
