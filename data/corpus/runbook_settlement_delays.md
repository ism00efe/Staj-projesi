# Runbook: Settlement and Reconciliation Delays

Symptom: captured payments are not appearing in settlement reports on time.

## Triage steps
1. Confirm the payments are in `captured` (not just `authorized`) state.
2. Compare the acquirer settlement file timestamp against the expected cut-off time.
3. Check for reconciliation mismatches: transaction count in our ledger vs. the acquirer
   file. A mismatch points to a missing or duplicated batch.

## Resolution
- Late acquirer file: settlement usually completes on the next cycle; monitor.
- Missing batch: re-request the settlement file from the acquirer.
- Duplicated batch: hold reconciliation and escalate to finance before adjusting ledgers.
