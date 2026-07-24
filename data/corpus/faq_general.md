# Frequently Asked Questions

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
