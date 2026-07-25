# Olay Sonrası Analiz (Postmortem): FAST Transfer Gecikmesi

**Özet:** 2026-06-15 tarihinde Havale/Fast Bridge üzerinden gönderilen transferlerin bir kısmı 10 dakikadan fazla gecikti (FAST'in beklenen anlık yanıt süresinin çok üzerinde).

**Kök Neden:** Alıcı taraftaki bir bankanın sistemi geçici olarak yavaş yanıt verdi; bizim tarafımızda kuyruk (queue) birikmesi oluştu.

**Etki:** ~800 transfer gecikmeli tamamlandı, hiçbiri kaybolmadı.

**Alınan Aksiyonlar:** Kuyruk için ayrı bir zaman aşımı ve uyarı eşiği tanımlandı. Bkz. `runbook_fast_failure.md`.
