# Runbook: PAY-9009 (fraud_suspected)

Category: risk · Safe to retry: No · Typical HTTP status: 403

## Symptom
Payments fail with `PAY-9009` — the risk engine blocks the payment before it reaches the issuer.

## Likely cause
Velocity rules, device reputation, or a mismatched billing profile.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-9009`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Route to manual review; never auto-retry a risk block.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
