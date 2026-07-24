# Runbook: Gateway Timeouts

Symptom: payments fail with `PAY-6006 gateway_timeout` or requests exceed the timeout
threshold.

## Triage steps
1. Check gateway latency dashboards for the affected time window.
2. Determine whether the timeout happened before or after the charge was submitted. If
   after, the payment may have actually succeeded — always resolve by status query, not by
   blind retry.
3. Verify the `Idempotency-Key` was sent; without it, a retry can double-charge.

## Resolution
- Safe retry: re-send the same request with the same `Idempotency-Key`.
- Uncertain state: call `GET /v1/payments/{id}` to get the authoritative status before
  retrying.
- Sustained timeouts: fail over to the secondary gateway and open an incident.
