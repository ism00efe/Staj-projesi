# FAQ: API Integration

**Q: Do I need to send a STAN on every authorization?**
A: Yes — the System Trace Audit Number (DE11) must be unique per request and is required to safely retry or reverse a transaction.

**Q: How do I paginate list endpoints?**
A: Cursor pagination via the `starting_after` query parameter.

**Q: What happens on a network timeout mid-authorization?**
A: The transaction state is uncertain — always query status via `api_authorization.md` before retrying; see `runbook_rc91.md`.
