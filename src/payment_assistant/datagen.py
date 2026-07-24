"""Synthetic dataset generator (v0, template-based).

Per the brief's priority order (working dataset > better dataset > advanced generator),
this v0 is deterministic and LLM-free: it writes a small, realistic English corpus of
payment-systems documents to ``CORPUS_DIR``. Some log samples contain fake-but-valid PII
(a Luhn-valid test card, a checksum-valid test TCKN, emails, IPs, phones) so that the
sanitization step can be demonstrated end to end.

Upgrade path: swap these templates for an LLM-driven or real-document loader without
touching the rest of the system (ingestion only reads files from a directory).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Documents (filename -> content). Prefixes drive doc_type in ingestion. ----------
_DOCS: dict[str, str] = {
    "api_payments.md": """# Payments API Reference

The Payments API lets you create and query card payments.

## Authentication
All requests require a Bearer token in the `Authorization` header. Tokens are issued per
merchant and must be kept secret. Example: `Authorization: Bearer <token>`.

## Create a payment
`POST /v1/payments`

Required fields: `amount` (minor units, integer), `currency` (ISO 4217), `card_token`,
and `merchant_reference`. To make retries safe, send an `Idempotency-Key` header with a
unique value per logical payment. Re-sending the same key returns the original result
instead of charging the customer twice.

### Response statuses
- `authorized` — funds held, not yet captured.
- `captured` — funds captured; money will settle.
- `declined` — issuer rejected the payment (see the `error_code` field).
- `failed` — a technical error occurred (gateway/network); safe to retry with the same
  `Idempotency-Key`.

## Query a payment
`GET /v1/payments/{id}` returns the current status and, if declined, the `error_code` and
`decline_reason`.
""",
    "api_refunds.md": """# Refunds API Reference

## Create a refund
`POST /v1/refunds`

Required fields: `payment_id`, `amount` (minor units). Partial refunds are allowed as long
as the cumulative refunded amount does not exceed the captured amount. Refunds are also
idempotent via the `Idempotency-Key` header.

## Rules
- A payment must be in `captured` state before it can be refunded.
- Refunds against `authorized`-only payments must first be voided, not refunded.
- Refund settlement can take 1-5 business days depending on the issuer.

## Common failures
- `refund_exceeds_captured` — requested amount is larger than what remains refundable.
- `payment_not_captured` — the payment has not been captured yet.
""",
    "errorcodes_payment.md": """# Payment Error Codes

| Code | Reason | Category | Retry? | Operator action |
|------|--------|----------|--------|-----------------|
| PAY-1001 | insufficient_funds | issuer decline | No | Ask customer to use another card or top up. |
| PAY-2002 | invalid_card | validation | No | Check card number/expiry; re-enter details. |
| PAY-3003 | expired_card | validation | No | Ask customer for a valid, non-expired card. |
| PAY-4004 | do_not_honor | issuer decline | No | Generic issuer decline; customer should contact bank. |
| PAY-5005 | 3ds_authentication_failed | authentication | Maybe | Retry 3D Secure; see runbook_3ds_failures. |
| PAY-6006 | gateway_timeout | technical | Yes | Retry with same Idempotency-Key; see runbook_gateway_timeouts. |
| PAY-7007 | duplicate_transaction | idempotency | No | Original transaction already processed; do not retry. |
| PAY-8008 | currency_not_supported | validation | No | Use a supported currency for the merchant. |
| PAY-9009 | fraud_suspected | risk | No | Payment blocked by risk engine; manual review required. |

Notes: only `technical` category errors (e.g. PAY-6006) are safe to auto-retry, and only
with the same `Idempotency-Key`.
""",
    "runbook_3ds_failures.md": """# Runbook: 3D Secure Authentication Failures

Symptom: payments fail with `PAY-5005 3ds_authentication_failed` or the 3DS challenge
window times out.

## Triage steps
1. Confirm the issuer supports 3DS2 for the card BIN. Older cards may fall back to 3DS1.
2. Check the ACS (Access Control Server) response code in the log. A missing `CRes`
   usually means the challenge was abandoned by the customer.
3. Look for `gateway_timeout` around the ACS call — a slow ACS can cause a timeout that
   surfaces as an authentication failure.

## Resolution
- Transient ACS timeout: retry the payment; the customer re-does the challenge.
- Repeated failures for one card: advise the customer to contact their bank; the card may
  be enrolled incorrectly.
- Merchant-wide spike: check the 3DS provider status page and open an incident.
""",
    "runbook_settlement_delays.md": """# Runbook: Settlement and Reconciliation Delays

Symptom: captured payments are not appearing in settlement reports on time.

## Triage steps
1. Confirm the payments are in `captured` (not just `authorized`) state.
2. Compare the acquirer settlement file timestamp against the expected cut-off time.
3. Check for reconciliation mismatches: transaction count in our ledger vs. the acquirer
   file. A mismatch points to a missing or duplicated batch.

## Resolution
- Late acquirer file: settlement usually completes on the next cycle; monitor.
- Missing batch: re-request the settlement file from the acquirer.
- Duplicated batch: hold reconciliation and escalate to finance before adjusting ledgers.
""",
    "runbook_gateway_timeouts.md": """# Runbook: Gateway Timeouts

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
""",
    "guide_declined_payments.md": """# Troubleshooting Guide: Declined Payments

When a payment is `declined`, read the `error_code` first — it determines whether a retry
can ever succeed.

## Decision flow
- `insufficient_funds` (PAY-1001) / `do_not_honor` (PAY-4004): issuer decline. Retrying
  the same card will not help; ask for another payment method.
- `invalid_card` (PAY-2002) / `expired_card` (PAY-3003): validation. Ask the customer to
  correct the card details.
- `3ds_authentication_failed` (PAY-5005): authentication. Retry the 3DS challenge once;
  if it fails again, escalate to runbook_3ds_failures.
- `fraud_suspected` (PAY-9009): do not retry; route to manual risk review.

## Anti-patterns
- Never auto-retry issuer declines in a loop — it can trigger issuer velocity blocks.
- Never retry without an `Idempotency-Key`.
""",
    "guide_webhook_verification.md": """# Troubleshooting Guide: Webhook Signature Verification

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
""",
    "faq_general.md": """# Frequently Asked Questions

**Q: What is an Idempotency-Key and when should I use it?**
A: A unique value you send on write requests (payments, refunds) so that retrying the same
request never causes a duplicate charge. Always use one on `POST /v1/payments`.

**Q: A payment failed with a gateway timeout. Is it safe to retry?**
A: Yes, but only with the same `Idempotency-Key`, and ideally after confirming status via
`GET /v1/payments/{id}`. See runbook_gateway_timeouts.

**Q: Why was my payment declined even though the card is valid?**
A: Declines with `do_not_honor` or `insufficient_funds` come from the issuer, not from us.
The customer should contact their bank or use another card.

**Q: How long do refunds take?**
A: 1-5 business days depending on the issuer.

**Q: What currencies are supported?**
A: Depends on the merchant configuration; unsupported currencies fail with PAY-8008.
""",
    "concept_idempotency.md": """# Concept: Idempotency in Payments

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
""",
    "concept_retries_backoff.md": """# Concept: Retries and Exponential Backoff

Not every failure should be retried, and retries must be paced.

## What to retry
- Retry *technical* failures: network errors, `gateway_timeout` (PAY-6006), HTTP 5xx.
- Do NOT retry *business* declines: `insufficient_funds`, `do_not_honor`, `invalid_card`.

## How to retry
Use exponential backoff with jitter: wait ~1s, then ~2s, ~4s, up to a cap, adding random
jitter to avoid thundering-herd retries. Always cap the number of attempts (e.g. 3-5) and
always reuse the same `Idempotency-Key`.
""",
    "concept_webhooks.md": """# Concept: Webhooks

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
""",
    # --- Log samples (contain fake, valid-format PII to exercise sanitization) --------
    "log_declined_payment.json": """{
  "timestamp": "2026-07-24T09:15:32Z",
  "level": "ERROR",
  "service": "payment-gateway",
  "event": "payment.declined",
  "payment_id": "pay_8fk2ld93",
  "error_code": "PAY-1001",
  "decline_reason": "insufficient_funds",
  "status": "declined",
  "amount": 24990,
  "currency": "TRY",
  "customer": {
    "email": "ahmet.yilmaz@example.com",
    "phone": "+90 532 123 45 67",
    "national_id": "10000000146"
  },
  "card": {
    "pan": "4111 1111 1111 1111",
    "expiry": "08/27"
  },
  "client_ip": "192.168.14.87",
  "message": "Issuer declined the transaction: insufficient funds"
}
""",
    "log_3ds_timeout.xml": """<?xml version="1.0" encoding="UTF-8"?>
<paymentLog>
  <timestamp>2026-07-24T10:02:11Z</timestamp>
  <event>threeds.challenge</event>
  <paymentId>pay_a1b2c3d4</paymentId>
  <status>failed</status>
  <errorCode>PAY-6006</errorCode>
  <message>ACS did not return CRes before gateway_timeout</message>
  <customerEmail>zeynep.demir@example.com</customerEmail>
  <customerPhone>0555 987 65 43</customerPhone>
  <clientIp>10.0.42.19</clientIp>
  <authToken>Bearer eyJhbGciOiJIUzI1NidemodemodemodemodemodemoXVCJ9.payload.signature</authToken>
</paymentLog>
""",
    "trace_nullpointer.txt": """ERROR 2026-07-24T11:44:05Z [capture-worker] Uncaught exception while capturing payment
java.lang.NullPointerException: Cannot invoke "PaymentGateway.capture(String)" because
        "this.gateway" is null
    at com.example.payments.CaptureWorker.capture(CaptureWorker.java:87)
    at com.example.payments.CaptureWorker.processBatch(CaptureWorker.java:54)
    at com.example.payments.Scheduler.run(Scheduler.java:33)
    at java.base/java.lang.Thread.run(Thread.java:1583)
Context: payment_id=pay_8fk2ld93, gateway=PRIMARY, attempt=2
Resolution hint: the primary gateway client was not initialized; see
runbook_gateway_timeouts for failover guidance.
""",
}


def generate_corpus(corpus_dir: str) -> int:
    """Write the synthetic corpus to ``corpus_dir``. Returns the number of files."""

    root = Path(corpus_dir)
    root.mkdir(parents=True, exist_ok=True)
    for filename, content in _DOCS.items():
        (root / filename).write_text(content, encoding="utf-8")
    logger.info("Generated %d synthetic documents in %s", len(_DOCS), corpus_dir)
    return len(_DOCS)
