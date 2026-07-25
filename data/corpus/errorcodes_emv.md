# EMV Chip Error Catalog

EMV chip transactions add cryptographic verification beyond the magstripe-era ISO 8583
flow. Common failure classes:

| Error | Meaning | Typical Cause |
|-------|---------|----------------|
| ARQC failure | The chip's Authorization Request Cryptogram doesn't validate against what the issuer expects | Corrupted chip, cloned/counterfeit card, or a card applet bug |
| Cryptogram mismatch | The issuer's host verification of the cryptogram fails during online authorization | Clock skew between terminal and issuer host, or a key management issue |
| TVR anomaly | Terminal Verification Results bitmap flags a risk condition (e.g. "offline PIN not performed", "card on exception file") | Terminal risk-management configuration, or a genuinely risky card/terminal combination |

ARQC and cryptogram failures should never be silently retried — they can indicate a
compromised card. See `runbook_arqc_failure.md` and `runbook_cryptogram_mismatch.md`.
