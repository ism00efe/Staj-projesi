# Takas ve Mutabakat Hata Kodları

| Kod | Anlam | Aksiyon |
|-----|-------|---------|
| batch_missing | Beklenen takas dosyası bankadan gelmedi | Bankadan dosyayı yeniden talep edin |
| batch_duplicate | Aynı batch iki kez işlenmiş | Mutabakatı durdurup finans ekibini bilgilendirin |
| amount_mismatch | İç kayıt ile banka dosyası tutarları uyuşmuyor | Satır satır karşılaştırma yapın |

Detaylı inceleme için bkz. `runbook_settlement_delay.md` ve
`postmortem_settlement_mismatch.md`.
