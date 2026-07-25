# FAST Hata Kodları

| Kod | Anlam | Yeniden Deneme |
|-----|-------|-----------------|
| receiver_bank_timeout | Alıcı bankanın sistemi zaman aşımına uğradı | Evet |
| account_not_found | Alıcı hesap/IBAN bulunamadı | Hayır |
| daily_limit_exceeded | Günlük FAST limiti aşıldı | Hayır |
| bridge_unavailable | Havale/Fast Bridge geçici olarak kullanılamıyor | Evet |

Bkz. `runbook_fast_failure.md` ve `concept_fast_payments.md`.
