# Troubleshooting Guide: Webhook Backlog

Symptom: events arrive hours late. Cause: your endpoint returns slowly or non-2xx, so deliveries queue behind retries. Fix: acknowledge with 200 immediately and process asynchronously.
