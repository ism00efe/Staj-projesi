"""Synthetic dataset generator (v1, parameterized templates).

Deterministic and LLM-free. Writes a realistic English corpus of payment-systems documents
to ``CORPUS_DIR``. Some log samples contain fake-but-valid PII (a Luhn-valid test card, a
checksum-valid test TCKN, emails, IPs, phones) so sanitization can be demonstrated end to
end.

v1 keeps the original hand-written documents (**with their original ids**, so existing
evaluation labels stay valid) and adds parameterized families generated from small
parameter tables — error-code runbooks, per-code JSON/XML logs, endpoint docs, concepts,
FAQs, stack traces, and guides.

Why the corpus was grown: with only 15 documents the retrieval benchmark was saturated
(recall@3 = 1.00) and a re-ranker asked to pick the top 20 of 15 chunks is a no-op. The
error-code runbooks are deliberately **near-identical in structure and differ only in
specifics** — precisely the case a bi-encoder blurs and a cross-encoder resolves.

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


# ---------------------------------------------------------------------------
# Parameterized families (v1)
# ---------------------------------------------------------------------------

# Each error code gets a runbook + a JSON log + an XML log. Structure is intentionally
# parallel across codes; only the specifics differ.
_ERROR_CODES: list[dict[str, str]] = [
    {
        "code": "PAY-1001", "slug": "pay1001", "reason": "insufficient_funds",
        "category": "issuer decline", "retry": "No",
        "symptom": "the issuer rejects the charge because the account lacks funds",
        "cause": "the cardholder's available balance is lower than the amount requested",
        "fix": "ask the customer for another payment method; do not retry the same card",
        "http": "402",
    },
    {
        "code": "PAY-2002", "slug": "pay2002", "reason": "invalid_card",
        "category": "validation", "retry": "No",
        "symptom": "the card number fails validation before reaching the issuer",
        "cause": "a mistyped PAN, a bad Luhn checksum, or an unsupported card scheme",
        "fix": "ask the customer to re-enter the card details carefully",
        "http": "400",
    },
    {
        "code": "PAY-3003", "slug": "pay3003", "reason": "expired_card",
        "category": "validation", "retry": "No",
        "symptom": "the expiry date is in the past at authorization time",
        "cause": "the stored card outlived its expiry, common for saved cards on file",
        "fix": "prompt the customer to update the expiry or add a new card",
        "http": "400",
    },
    {
        "code": "PAY-4004", "slug": "pay4004", "reason": "do_not_honor",
        "category": "issuer decline", "retry": "No",
        "symptom": "a generic issuer refusal with no specific reason returned",
        "cause": "issuer-side risk rules; the network deliberately hides the detail",
        "fix": "advise the customer to contact their bank, or try another card",
        "http": "402",
    },
    {
        "code": "PAY-5005", "slug": "pay5005", "reason": "3ds_authentication_failed",
        "category": "authentication", "retry": "Maybe",
        "symptom": "the 3-D Secure challenge does not complete successfully",
        "cause": "an abandoned challenge, a slow ACS, or incorrect card enrolment",
        "fix": "retry the 3DS challenge once; on repeat failure escalate to the issuer",
        "http": "401",
    },
    {
        "code": "PAY-6006", "slug": "pay6006", "reason": "gateway_timeout",
        "category": "technical", "retry": "Yes",
        "symptom": "the upstream gateway does not respond within the timeout window",
        "cause": "network latency or gateway saturation; the charge state is uncertain",
        "fix": "query the payment status first, then retry with the same Idempotency-Key",
        "http": "504",
    },
    {
        "code": "PAY-7007", "slug": "pay7007", "reason": "duplicate_transaction",
        "category": "idempotency", "retry": "No",
        "symptom": "a charge matching an already-processed request is submitted again",
        "cause": "a retry sent without reusing the original Idempotency-Key",
        "fix": "treat the original transaction as authoritative; never retry this code",
        "http": "409",
    },
    {
        "code": "PAY-8008", "slug": "pay8008", "reason": "currency_not_supported",
        "category": "validation", "retry": "No",
        "symptom": "the requested currency is not enabled for the merchant account",
        "cause": "merchant configuration does not include the requested ISO 4217 currency",
        "fix": "use a configured currency or request enablement from onboarding",
        "http": "400",
    },
    {
        "code": "PAY-9009", "slug": "pay9009", "reason": "fraud_suspected",
        "category": "risk", "retry": "No",
        "symptom": "the risk engine blocks the payment before it reaches the issuer",
        "cause": "velocity rules, device reputation, or a mismatched billing profile",
        "fix": "route to manual review; never auto-retry a risk block",
        "http": "403",
    },
]

_ENDPOINTS: list[tuple[str, str, str, str]] = [
    ("captures", "POST /v1/captures", "capture a previously authorized payment",
     "Requires `payment_id`. Only `authorized` payments can be captured, and only once."),
    ("voids", "POST /v1/voids", "release an authorization without capturing",
     "Voids apply to `authorized` payments; a captured payment must be refunded instead."),
    ("payouts", "POST /v1/payouts", "send funds to a connected account",
     "Requires `destination` and `amount`. Payouts settle on the next banking cycle."),
    ("disputes", "GET /v1/disputes", "list chargebacks raised against payments",
     "Each dispute carries a `reason_code` and an evidence submission deadline."),
    ("tokens", "POST /v1/tokens", "exchange raw card details for a reusable token",
     "Raw PAN never touches merchant servers; tokens are scoped per merchant."),
    ("customers", "POST /v1/customers", "store a customer profile for repeat payments",
     "Customers may hold multiple saved card tokens; deletion is irreversible."),
    ("balances", "GET /v1/balances", "read available and pending balances",
     "Pending funds become available after the settlement window closes."),
    ("subscriptions", "POST /v1/subscriptions", "bill a customer on a recurring schedule",
     "Recurring charges are exempt from 3DS where regulation allows a MIT exemption."),
]

_CONCEPTS: list[tuple[str, str, str]] = [
    ("settlement", "Settlement",
     "Settlement is the movement of captured funds from the acquirer to the merchant bank "
     "account. It happens in batches on a cut-off schedule, so a captured payment is not "
     "instantly money in the bank. Settlement reports reconcile our ledger against the "
     "acquirer file."),
    ("chargebacks", "Chargebacks",
     "A chargeback is a forced reversal initiated by the cardholder's issuer. The merchant "
     "may submit evidence before a deadline. Losing a dispute returns the funds to the "
     "cardholder and adds a fee. High chargeback ratios risk scheme monitoring programs."),
    ("pci_scope", "PCI DSS Scope",
     "Any system that stores, processes, or transmits raw card data falls in PCI DSS "
     "scope. Tokenization keeps the PAN out of merchant systems, shrinking scope. Logs "
     "must never contain a full PAN; masking is mandatory before storage."),
    ("fx_conversion", "Currency Conversion",
     "Cross-currency payments apply an FX rate at authorization or at settlement, "
     "depending on scheme rules. The rate quoted to the customer may differ from the "
     "settled rate, producing small reconciliation differences."),
    ("tokenization", "Tokenization",
     "Tokenization replaces a card number with a surrogate value usable only by the "
     "merchant it was issued to. Tokens survive card expiry via account updater services "
     "and are the basis for saved-card and subscription flows."),
    ("reconciliation", "Reconciliation",
     "Reconciliation matches internal transaction records against acquirer settlement "
     "files line by line. Mismatches indicate a missing batch, a duplicated batch, or a "
     "timing difference across the cut-off."),
]

_FAQ_TOPICS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("refunds", "Refunds", [
        ("How long does a refund take?", "1-5 business days depending on the issuer."),
        ("Can I refund more than was captured?",
         "No — that fails with `refund_exceeds_captured`."),
        ("Can I refund an authorized-only payment?",
         "No. Void it instead; refunds require a captured payment."),
    ]),
    ("threedsecure", "3-D Secure", [
        ("When is 3DS required?", "Where regulation mandates SCA for the transaction."),
        ("Why did the challenge time out?",
         "A slow or unreachable ACS; see PAY-5005 and PAY-6006."),
        ("Are subscriptions challenged?",
         "Usually not — merchant-initiated transactions often qualify for an exemption."),
    ]),
    ("webhooks", "Webhooks", [
        ("Why is my signature check failing?",
         "You are hashing a re-serialized body; hash the raw bytes."),
        ("Are webhooks ordered?", "No. Use event timestamps, not arrival order."),
        ("How long are webhooks retried?",
         "With exponential backoff for up to 24 hours on non-2xx responses."),
    ]),
    ("fees", "Fees and Pricing", [
        ("When are fees deducted?", "At settlement, netted off the batch total."),
        ("Are refunds free?", "The original processing fee is generally not returned."),
        ("What does a chargeback cost?", "A fixed dispute fee plus the disputed amount."),
    ]),
    ("testing", "Testing and Sandbox", [
        ("Which test card always declines?",
         "Use the sandbox PAN mapped to `insufficient_funds` (PAY-1001)."),
        ("Does sandbox settle?", "No — settlement is simulated on an accelerated clock."),
        ("Can I force a timeout?",
         "Yes, the sandbox exposes a trigger amount that returns PAY-6006."),
    ]),
    ("integration", "Integration", [
        ("Do I need an Idempotency-Key?", "Yes, on every POST that moves money."),
        ("How do I paginate list endpoints?", "Cursor pagination via the `starting_after` parameter."),
        ("What is the API rate limit?", "Requests are throttled per merchant; 429 means back off."),
    ]),
]

_TRACES: list[tuple[str, str, str, str]] = [
    ("timeout_capture", "java.net.SocketTimeoutException", "Read timed out",
     "com.example.payments.GatewayClient.capture(GatewayClient.java:142)"),
    ("json_parse", "com.fasterxml.jackson.core.JsonParseException",
     "Unexpected character ('<' (code 60))",
     "com.example.payments.WebhookParser.parse(WebhookParser.java:61)"),
    ("db_deadlock", "org.postgresql.util.PSQLException",
     "deadlock detected during ledger update",
     "com.example.ledger.LedgerWriter.commit(LedgerWriter.java:203)"),
    ("signature_mismatch", "java.security.SignatureException",
     "HMAC mismatch on webhook payload",
     "com.example.payments.SignatureVerifier.verify(SignatureVerifier.java:47)"),
    ("null_token", "java.lang.IllegalStateException",
     "card token was null for saved-card charge",
     "com.example.payments.TokenResolver.resolve(TokenResolver.java:88)"),
]

_GUIDES: list[tuple[str, str, str]] = [
    ("retry_storms", "Retry Storms",
     "Symptom: a spike of repeated authorizations after an outage. Cause: clients retrying "
     "without backoff or idempotency keys. Fix: enforce exponential backoff with jitter, "
     "cap attempts, and require an Idempotency-Key on every write."),
    ("partial_captures", "Partial Captures",
     "Symptom: the captured total is less than authorized and the remainder never clears. "
     "Cause: an authorization expires before the second capture. Fix: capture the full "
     "amount or re-authorize the remainder before the hold expires."),
    ("webhook_backlog", "Webhook Backlog",
     "Symptom: events arrive hours late. Cause: your endpoint returns slowly or non-2xx, "
     "so deliveries queue behind retries. Fix: acknowledge with 200 immediately and process "
     "asynchronously."),
    ("currency_mismatch", "Currency Mismatch",
     "Symptom: PAY-8008 on a previously working integration. Cause: the merchant account "
     "lost a currency configuration or the client hardcoded a currency. Fix: read supported "
     "currencies from the account endpoint."),
    ("saved_card_failures", "Saved Card Failures",
     "Symptom: stored cards start declining in bulk. Cause: mass expiry without account "
     "updater. Fix: enable the updater and prompt customers before expiry dates lapse."),
]


def _runbook_for_code(ec: dict[str, str]) -> tuple[str, str]:
    name = f"runbook_err_{ec['slug']}.md"
    body = f"""# Runbook: {ec['code']} ({ec['reason']})

Category: {ec['category']} · Safe to retry: {ec['retry']} · Typical HTTP status: {ec['http']}

## Symptom
Payments fail with `{ec['code']}` — {ec['symptom']}.

## Likely cause
{ec['cause'].capitalize()}.

## Triage steps
1. Confirm the `error_code` on the payment is exactly `{ec['code']}`.
2. Check whether the failure is isolated to one card/customer or merchant-wide.
3. For merchant-wide spikes, compare against gateway status and recent deploys.

## Resolution
{ec['fix'].capitalize()}.

## Retry policy
Retry allowed: {ec['retry']}. Only `technical` category failures are safe to auto-retry,
and only when the original `Idempotency-Key` is reused.
"""
    return name, body


def _json_log_for_code(ec: dict[str, str]) -> tuple[str, str]:
    name = f"log_err_{ec['slug']}.json"
    body = f"""{{
  "timestamp": "2026-07-24T12:{ec['slug'][-2:]}:07Z",
  "level": "ERROR",
  "service": "payment-gateway",
  "event": "payment.failed",
  "payment_id": "pay_{ec['slug']}x7",
  "error_code": "{ec['code']}",
  "decline_reason": "{ec['reason']}",
  "status": "failed",
  "http_status": {ec['http']},
  "customer": {{
    "email": "customer.{ec['slug']}@example.com",
    "phone": "+90 533 000 11 22"
  }},
  "card": {{ "pan": "4111 1111 1111 1111" }},
  "client_ip": "10.12.0.44",
  "message": "{ec['symptom'].capitalize()}"
}}
"""
    return name, body


def _xml_log_for_code(ec: dict[str, str]) -> tuple[str, str]:
    name = f"log_err_{ec['slug']}.xml"
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<paymentLog>
  <timestamp>2026-07-24T13:{ec['slug'][-2:]}:19Z</timestamp>
  <event>payment.failed</event>
  <paymentId>pay_{ec['slug']}q3</paymentId>
  <status>failed</status>
  <errorCode>{ec['code']}</errorCode>
  <declineReason>{ec['reason']}</declineReason>
  <message>{ec['symptom'].capitalize()}</message>
  <customerEmail>ops.{ec['slug']}@example.com</customerEmail>
  <clientIp>192.168.7.31</clientIp>
</paymentLog>
"""
    return name, body


def _generated_docs() -> dict[str, str]:
    """Build the parameterized document families."""

    docs: dict[str, str] = {}

    for ec in _ERROR_CODES:
        for builder in (_runbook_for_code, _json_log_for_code, _xml_log_for_code):
            name, body = builder(ec)
            docs[name] = body

    for slug, endpoint, purpose, detail in _ENDPOINTS:
        docs[f"api_{slug}.md"] = (
            f"# {slug.capitalize()} API Reference\n\n"
            f"`{endpoint}` — {purpose}.\n\n"
            f"## Usage\n{detail}\n\n"
            "## Idempotency\nSend an `Idempotency-Key` header on every write request so a "
            "retry never duplicates the operation.\n\n"
            "## Errors\nValidation failures return 4xx with an `error_code`; upstream "
            "failures return `PAY-6006 gateway_timeout` and are safe to retry.\n"
        )

    for slug, title, text in _CONCEPTS:
        docs[f"concept_{slug}.md"] = f"# Concept: {title}\n\n{text}\n"

    for slug, title, qas in _FAQ_TOPICS:
        lines = [f"# FAQ: {title}\n"]
        for question, answer in qas:
            lines.append(f"**Q: {question}**\nA: {answer}\n")
        docs[f"faq_{slug}.md"] = "\n".join(lines)

    for slug, exc, message, frame in _TRACES:
        docs[f"trace_{slug}.txt"] = (
            f"ERROR 2026-07-24T14:05:00Z [payments-worker] Unhandled exception\n"
            f"{exc}: {message}\n"
            f"    at {frame}\n"
            "    at com.example.payments.Dispatcher.dispatch(Dispatcher.java:75)\n"
            "    at java.base/java.lang.Thread.run(Thread.java:1583)\n"
            f"Context: component={slug}, attempt=2\n"
        )

    for slug, title, text in _GUIDES:
        docs[f"guide_{slug}.md"] = f"# Troubleshooting Guide: {title}\n\n{text}\n"

    return docs


def generate_corpus(corpus_dir: str) -> int:
    """Write the synthetic corpus to ``corpus_dir``. Returns the number of files.

    Writes the curated documents first (preserving their original ids) and then the
    parameterized families.
    """

    root = Path(corpus_dir)
    root.mkdir(parents=True, exist_ok=True)

    all_docs = {**_DOCS, **_generated_docs()}
    for filename, content in all_docs.items():
        (root / filename).write_text(content, encoding="utf-8")

    logger.info("Generated %d synthetic documents in %s", len(all_docs), corpus_dir)
    return len(all_docs)
