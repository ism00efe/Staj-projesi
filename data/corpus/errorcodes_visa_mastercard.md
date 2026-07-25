# Card Scheme Decline Code Cross-Reference

Card schemes publish their own decline codes, which our system maps onto the internal
RC catalog (`errorcodes_iso8583.md`) at the gateway layer.

| Scheme | Code | Scheme Reason | Internal Equivalent |
|--------|------|----------------|----------------------|
| Visa | 05 | Do Not Honor | RC-05 |
| Visa | 14 | Invalid Account Number | RC-14 |
| Visa | 51 | Insufficient Funds | RC-51 |
| Visa | 54 | Expired Card | RC-54 |
| Visa | 62 | Restricted Card | RC-62 |
| Mastercard | 04 | Pick Up Card | RC-62 (Kısıtlı Kart) |
| Mastercard | 05 | Do Not Honor | RC-05 |
| Mastercard | 51 | Insufficient Funds | RC-51 |
| Mastercard | 54 | Expired Card | RC-54 |
| Mastercard | 57 | Transaction Not Permitted to Cardholder | RC-12 / RC-62 |
| Mastercard | 62 | Restricted Card | RC-62 |

Notes:
- Mastercard 04 (Pick Up Card): Kartın el konulması istenir; genellikle kayıp/çalıntı bildirimiyle ilişkilidir.
- Mastercard 57 (Transaction Not Permitted to Cardholder): Kart sahibi için bu işlem tipi (örn. yurt dışı, taksitli) izinli değil.

The mapping is not always 1:1 — some scheme codes (e.g. Mastercard 04) fold into a
broader internal category. See `runbook_rc62.md` for the restricted-card triage flow.
