# Runbook: PAY-6006 (gateway_timeout)

Category: technical · Safe to retry: Yes · Typical HTTP status: 504

## Symptom
Payments fail with `PAY-6006` — the upstream gateway does not respond within the timeout window.

## Likely cause
Network latency or gateway saturation; the charge state is uncertain.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-6006`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Query the payment status first, then retry with the same idempotency-key.

## Retry policy
Retry allowed: Yes. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
