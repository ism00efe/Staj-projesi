# Runbook: 3D Secure Authentication Failures

Symptom: payments fail with `PAY-5005 3ds_authentication_failed` or the 3DS challenge
window times out.

## Triage steps
1. Confirm the issuer supports 3DS2 for the card BIN. Older cards may fall back to 3DS1.
2. Check the ACS (Access Control Server) response code in the log. A missing `CRes`
   usually means the challenge was abandoned by the customer.
3. Look for `gateway_timeout` around the ACS call — a slow ACS can cause a timeout that
   surfaces as an authentication failure.

## Resolution
- Transient ACS timeout: retry the payment; the customer re-does the challenge.
- Repeated failures for one card: advise the customer to contact their bank; the card may
  be enrolled incorrectly.
- Merchant-wide spike: check the 3DS provider status page and open an incident.
