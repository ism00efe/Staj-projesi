# Concept: ISO 8583 Message Structure

ISO 8583 defines the message format most card networks use for financial transactions. Message Type Indicators (MTIs) identify the message's purpose: `0100` (authorization request), `0110` (authorization response), `0420` (reversal request), `0430` (reversal response). Each message carries a set of Data Elements (DEs) — e.g. DE2 (PAN), DE3 (processing code), DE4 (amount), DE11 (STAN), DE37 (RRN), DE39 (response code). See `errorcodes_iso8583.md` for the full response code table used across this system.
