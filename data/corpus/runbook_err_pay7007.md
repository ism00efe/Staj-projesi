# Runbook: PAY-7007 (duplicate_transaction)

Category: idempotency · Safe to retry: No · Typical HTTP status: 409

## Symptom
Payments fail with `PAY-7007` — a charge matching an already-processed request is submitted again.

## Likely cause
A retry sent without reusing the original idempotency-key.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-7007`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Treat the original transaction as authoritative; never retry this code.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
