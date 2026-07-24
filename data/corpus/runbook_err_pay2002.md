# Runbook: PAY-2002 (invalid_card)

Category: validation · Safe to retry: No · Typical HTTP status: 400

## Symptom
Payments fail with `PAY-2002` — the card number fails validation before reaching the issuer.

## Likely cause
A mistyped pan, a bad luhn checksum, or an unsupported card scheme.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-2002`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Ask the customer to re-enter the card details carefully.

## Retry policy
Retry allowed: No. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
