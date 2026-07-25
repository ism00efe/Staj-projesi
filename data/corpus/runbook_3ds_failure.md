# Prosedür: 3DS Kimlik Doğrulama Hatası

Kategori: kimlik doğrulama · Yeniden deneme: Belki

## Belirti
Kart hazır olmayan işlemler 3DS zorlu doğrulama (challenge) tamamlanamadığı için
başarısız oluyor.

## Olası Neden
ACS (Access Control Server) yanıt vermiyor, kart sahibi zorlu doğrulama penceresini
kapattı, ya da kart hatalı kayıtlı (enrollment sorunu). Bkz. `errorcodes_3ds.md`.

## İnceleme Adımları
1. Hatanın `errorcodes_3ds.md` içindeki hangi kategoriye girdiğini belirleyin.
2. ACS zaman aşımı şüphesi varsa 3DS sağlayıcı durum sayfasını kontrol edin.
3. Merchant genelinde bir artış varsa `postmortem_3ds_provider_outage.md` dosyasındaki
   emsal olaya bakın.

## Çözüm
Geçici ACS zaman aşımı: zorlu doğrulamayı bir kez daha deneyin. Tekrarlayan hatalarda
kart sahibini bankasıyla iletişime geçirin.
