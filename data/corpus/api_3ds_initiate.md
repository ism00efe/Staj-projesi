# 3Ds Initiate API Reference

`POST /v1/3ds/initiate` — start a 3-D Secure / SCA (Strong Customer Authentication) challenge.

## Usage
Required for most card-not-present transactions under current SCA rules. On completion the issuer's ACS returns a cryptographic result consumed by the authorization call. See `errorcodes_3ds.md` and `guide_3ds_enrollment.md`.

## Idempotency
Send a unique `stan` (System Trace Audit Number) on every write request so a retry never duplicates the operation — see `concept_iso8583_overview.md`.

## Errors
Validation failures return an internal RC in the 4xx-equivalent range with a `response_code`; upstream/technical failures return RC-91 or RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.
