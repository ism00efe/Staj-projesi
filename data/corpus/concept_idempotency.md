# Concept: Idempotency in Payments

An operation is *idempotent* if performing it multiple times has the same effect as
performing it once. In payments this is critical: networks are unreliable, and a client
may retry a request whose response was lost.

## How it works here
- The client generates a unique `Idempotency-Key` per logical operation.
- The server stores the key with the result of the first successful processing.
- Any later request with the same key returns the stored result instead of re-executing.

## Why it matters
Without idempotency, a timeout-then-retry can charge a customer twice. Keys should be
persisted long enough to cover realistic retry windows (typically 24 hours).
