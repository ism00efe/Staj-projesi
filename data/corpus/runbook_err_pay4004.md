# Runbook: PAY-4004 (do_not_honor)

Category: issuer decline · Safe to retry: No · Typical HTTP status: 402

## Symptom
Payments fail with `PAY-4004` — a generic issuer refusal with no specific reason returned.

## Likely cause
Issuer-side risk rules; the network deliberately hides the detail.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-4004`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Advise the customer to contact their bank, or try another card.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
