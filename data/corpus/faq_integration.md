# FAQ: Integration

**Q: Do I need an Idempotency-Key?**
A: Yes, on every POST that moves money.

**Q: How do I paginate list endpoints?**
A: Cursor pagination via the `starting_after` parameter.

**Q: What is the API rate limit?**
A: Requests are throttled per merchant; 429 means back off.
