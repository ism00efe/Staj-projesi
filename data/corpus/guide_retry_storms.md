# Troubleshooting Guide: Retry Storms

Symptom: a spike of repeated authorizations after an outage. Cause: clients retrying without backoff or idempotency keys. Fix: enforce exponential backoff with jitter, cap attempts, and require an Idempotency-Key on every write.
