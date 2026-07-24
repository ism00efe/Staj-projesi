# Payment Error Codes

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
