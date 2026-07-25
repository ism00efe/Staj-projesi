# FAQ: 3-D Secure

**Q: When is a 3DS challenge required?**
A: Whenever regulation mandates Strong Customer Authentication (SCA) for the transaction — most card-not-present payments above a low-value threshold.

**Q: Why did the challenge time out?**
A: A slow or unreachable ACS (Access Control Server); see `errorcodes_3ds.md` and `runbook_3ds_failure.md`.

**Q: Are recurring charges challenged every time?**
A: Usually not — merchant-initiated recurring transactions can qualify for an SCA exemption if the initial charge was customer-initiated and challenged.
