# Olay Sonrası Analiz (Postmortem): 3DS Sağlayıcı Kesintisi

**Özet:** 2026-06-29 tarihinde harici 3DS sağlayıcısının ACS servisi 25 dakika boyunca yanıt vermedi.

**Kök Neden:** Sağlayıcı tarafında bölgesel bir altyapı sorunu (bizim sistemimizde bir hata tespit edilmedi).

**Etki:** Kart hazır olmayan (card-not-present) işlemlerin çoğu RC-91 benzeri bir zaman aşımıyla başarısız oldu.

**Alınan Aksiyonlar:** İkincil bir 3DS sağlayıcısına otomatik geçiş (failover) mekanizması eklendi. Bkz. `runbook_3ds_failure.md`.
