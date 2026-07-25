# FAQ: Refunds

**Q: How long does a refund take to settle?**
A: 1-3 business days, following the standard clearing (takas) cycle.

**Q: Can I refund more than the captured amount?**
A: No — that fails with an `Invalid Transaction` style rejection; see `api_refund.md`.

**Q: Can an authorization-only transaction be refunded?**
A: No — void it with `api_reversal.md` instead; refunds require a captured transaction.
