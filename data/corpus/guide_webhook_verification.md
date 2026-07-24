# Troubleshooting Guide: Webhook Signature Verification

Webhooks notify your system of payment events (e.g. `payment.captured`). Each webhook is
signed so you can verify it really came from us.

## How verification works
Every webhook includes a `X-Signature` header: an HMAC-SHA256 of the raw request body,
keyed with your webhook secret. Recompute the HMAC over the *raw* body and compare.

## Common problems
- Signature mismatch: you are almost certainly hashing a re-serialized body. Hash the raw
  bytes exactly as received.
- Missing events: verify your endpoint returns HTTP 200 quickly; we retry with exponential
  backoff on non-2xx responses and eventually stop.
- Clock/timestamp errors: reject webhooks whose timestamp is older than 5 minutes to
  prevent replay.
