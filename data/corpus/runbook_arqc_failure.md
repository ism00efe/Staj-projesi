# Runbook: ARQC Failure

Category: EMV / technical · Retry: No (do not blindly retry a cryptogram failure)

## Symptom
Kartlı Ödeme Motoru (KÖM) rejects a chip transaction because the Authorization Request Cryptogram
(ARQC) submitted by the card does not validate against the issuer's expected value.

## Likely cause
A corrupted or malfunctioning chip, a cloned/counterfeit card, or (rarely) an applet
bug on a specific card batch. See `errorcodes_emv.md`.

## Triage steps
1. Confirm this is isolated to one card, not a batch of cards from the same issuer.
2. Check whether the terminal firmware version matches the certified EMV kernel
   version — a mismatch can corrupt cryptogram generation.
3. If concentrated on one card, do not retry; this can indicate fraud.

## Resolution
Ask the cardholder to try a different card or a contactless/magstripe fallback where
permitted. Escalate a cluster of ARQC failures to the risk team immediately.
