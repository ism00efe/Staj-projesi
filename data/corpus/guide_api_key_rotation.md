# Configuration Guide: API Key Rotation

Rotate merchant API keys every 90 days or immediately after a suspected leak: (1) generate a new key pair in Merchant Portal, (2) deploy the new key to your integration alongside the old one, (3) confirm traffic on the new key, (4) revoke the old key. Never share a live key outside your own backend — client-side code should only ever see a tokenization-scoped key (`api_tokenization.md`).
