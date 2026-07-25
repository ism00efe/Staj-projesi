# 3-D Secure / SCA Error Catalog

| Error | Meaning | Retry? |
|-------|---------|--------|
| challenge_timeout | The ACS did not return a challenge result within the timeout window | Maybe — retry the challenge once |
| challenge_abandoned | The cardholder closed the challenge window without completing it | No — ask the cardholder to try again |
| acs_unavailable | The issuer's ACS could not be reached | Yes — treat like RC-91 |
| authentication_failed | The cardholder failed the challenge (wrong OTP, etc.) | No |

See `api_3ds_initiate.md` for the request flow and `runbook_3ds_failure.md` for triage.
