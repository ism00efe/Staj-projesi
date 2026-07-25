# Olay Sonrası Analiz (Postmortem): Takas Mutabakatsızlığı

**Özet:** 2026-07-10 takas döngüsünde Takas Motoru'nun ürettiği toplam tutar, banka takas dosyasıyla ~%2 oranında uyuşmadı.

**Kök Neden:** Aynı batch iki kez işlenmiş (mükerrer gönderim), önceki bir yeniden deneme (retry) mekanizmasının idempotency kontrolü atlaması nedeniyle.

**Etki:** Mutabakat 6 saat gecikti; finansal düzeltme manuel yapıldı.

**Alınan Aksiyonlar:** Batch gönderimine idempotency anahtarı eklendi. Bkz. `runbook_settlement_delay.md`.
