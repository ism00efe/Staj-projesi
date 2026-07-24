# Runbook: PAY-1001 (insufficient_funds)

Category: issuer decline · Safe to retry: No · Typical HTTP status: 402

## Symptom
Payments fail with `PAY-1001` — the issuer rejects the charge because the account lacks funds.

## Likely cause
The cardholder's available balance is lower than the amount requested.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-1001`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Ask the customer for another payment method; do not retry the same card.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
