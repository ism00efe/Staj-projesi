# SSS: Provizyon Süreçleri

**S: Açık provizyon ile kapalı provizyon arasındaki fark nedir?**
C: Açık provizyon, tutarın kart sahibinin hesabında bloke edilip henüz tahsil edilmediği durumdur (authorization). Kapalı provizyon ise tutarın fiilen tahsil edildiği (capture) durumdur. Bkz. `api_capture.md`.

**S: Açık provizyon ne kadar süre bekletilebilir?**
C: Şemaya göre değişir; genellikle 7 gün içinde kapatılmayan (capture edilmeyen) açık provizyonlar otomatik olarak düşer.

**S: Provizyon RC-91 ile reddedilirse ne yapmalıyım?**
C: Önce işlem durumunu sorgulayın, ardından aynı STAN ile tekrar deneyin. Bkz. `runbook_rc91.md`.
