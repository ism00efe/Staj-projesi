# Olay Sonrası Analiz (Postmortem): Webhook Teslimat Birikmesi

**Özet:** 2026-06-02 tarihinde bir üye işyerinin webhook uç noktası yavaş yanıt vermeye başladı, bu da teslimat kuyruğunda birikmeye yol açtı.

**Kök Neden:** Üye işyeri entegrasyonu webhook isteğini senkron olarak işliyordu; kendi sistemlerindeki bir yavaşlama bizim yeniden deneme (retry) mekanizmamızı tetikledi.

**Etki:** Bazı `payment.captured` olayları 3 saate kadar gecikmeli iletildi.

**Alınan Aksiyonlar:** Üye işyerine hızlı HTTP 200 dönüp işlemi asenkron yapması önerildi; bkz. `guide_webhook_setup.md`.
