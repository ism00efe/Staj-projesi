# FAQ: Webhooks

**Q: Why is my signature check failing?**
A: You are hashing a re-serialized body; hash the raw bytes.

**Q: Are webhooks ordered?**
A: No. Use event timestamps, not arrival order.

**Q: How long are webhooks retried?**
A: With exponential backoff for up to 24 hours on non-2xx responses.
