# Tokenization API Reference

`POST /v1/tokens` — exchange a raw PAN for a reusable token.

## Usage
The raw PAN never touches merchant systems after tokenization, keeping merchants out of PCI DSS scope for card storage — see `concept_pci_scope.md`.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
