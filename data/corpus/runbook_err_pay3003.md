# Runbook: PAY-3003 (expired_card)

Category: validation · Safe to retry: No · Typical HTTP status: 400

## Symptom
Payments fail with `PAY-3003` — the expiry date is in the past at authorization time.

## Likely cause
The stored card outlived its expiry, common for saved cards on file.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-3003`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Prompt the customer to update the expiry or add a new card.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
