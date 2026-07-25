# Runbook: Cryptogram Mismatch

Category: EMV / technical · Retry: Maybe

## Symptom
The issuer's host-side cryptogram verification fails during online authorization,
distinct from a terminal-side ARQC failure.

## Likely cause
Clock skew between the terminal and the issuer host, or a key-management
synchronization issue on the issuer side. See `errorcodes_emv.md`.

## Triage steps
1. Confirm the terminal's clock is synchronized (NTP) — skew is the most common cause.
2. Check whether the issue is isolated to one issuer's BIN range.
3. If terminal clock is correct, escalate to the issuer via Kartlı Ödeme Motoru (KÖM) support.

## Resolution
A single retry is safe if the terminal clock was the cause and has been corrected.
Persistent mismatches for one issuer require escalation, not repeated retries.
