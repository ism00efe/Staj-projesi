# Concept: Webhooks

A webhook is an HTTP callback we send to your endpoint when an event occurs, so you do not
have to poll. Typical events: `payment.authorized`, `payment.captured`,
`payment.declined`, `refund.succeeded`.

## Delivery guarantees
- At-least-once: you may receive the same event more than once; deduplicate by event id.
- Retries: non-2xx responses are retried with exponential backoff for up to 24 hours.
- Ordering: not guaranteed; use event timestamps, not arrival order.

## Security
Verify the `X-Signature` HMAC on every webhook and reject stale timestamps. See
guide_webhook_verification.
