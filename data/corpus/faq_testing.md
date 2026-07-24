# FAQ: Testing and Sandbox

**Q: Which test card always declines?**
A: Use the sandbox PAN mapped to `insufficient_funds` (PAY-1001).

**Q: Does sandbox settle?**
A: No — settlement is simulated on an accelerated clock.

**Q: Can I force a timeout?**
A: Yes, the sandbox exposes a trigger amount that returns PAY-6006.
