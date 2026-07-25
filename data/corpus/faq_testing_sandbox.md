# FAQ: Testing and Sandbox

**Q: Which test card triggers a decline?**
A: Sandbox PANs are mapped to specific response codes for testing — see `errorcodes_iso8583.md` for the code table your test card should trigger.

**Q: Does the sandbox settle transactions?**
A: No — settlement is simulated on an accelerated clock, not a real clearing cycle.

**Q: Can I simulate an issuer timeout?**
A: Yes, the sandbox exposes a trigger amount that returns RC-91.
