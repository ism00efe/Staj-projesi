# Concept: Retries and Exponential Backoff

Not every failure should be retried, and retries must be paced.

## What to retry
- Retry *technical* failures: network errors, `gateway_timeout` (PAY-6006), HTTP 5xx.
- Do NOT retry *business* declines: `insufficient_funds`, `do_not_honor`, `invalid_card`.

## How to retry
Use exponential backoff with jitter: wait ~1s, then ~2s, ~4s, up to a cap, adding random
jitter to avoid thundering-herd retries. Always cap the number of attempts (e.g. 3-5) and
always reuse the same `Idempotency-Key`.
