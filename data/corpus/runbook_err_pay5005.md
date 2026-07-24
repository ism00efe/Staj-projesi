# Runbook: PAY-5005 (3ds_authentication_failed)

Category: authentication · Safe to retry: Maybe · Typical HTTP status: 401

## Symptom
Payments fail with `PAY-5005` — the 3-D Secure challenge does not complete successfully.

## Likely cause
An abandoned challenge, a slow acs, or incorrect card enrolment.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `PAY-5005`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
Retry the 3ds challenge once; on repeat failure escalate to the issuer.

## Retry policy
Retry allowed: Maybe. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
