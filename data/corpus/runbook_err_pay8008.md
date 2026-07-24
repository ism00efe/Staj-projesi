# Runbook: PAY-8008 (currency_not_supported)

Category: validation · Safe to retry: No · Typical HTTP status: 400

## Symptom
Payments fail with `PAY-8008` — the requested currency is not enabled for the merchant account.

## Likely cause
Merchant configuration does not include the requested iso 4217 currency.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-8008`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Use a configured currency or request enablement from onboarding.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
