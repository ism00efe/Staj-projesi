# Prosedür: RC-54 (Kartın Süresi Dolmuş / Expired Card)

Kategori: doğrulama · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-54` yanıt koduyla reddediyor: provizyon anında kartın son kullanma tarihi geçmiş durumda.

## Olası Neden
Kayıtlı (saklanmış) kartlarda sık görülür: kart süresi dolmuş ama hesap güncelleme servisi (account updater) henüz yeni kart bilgisini almamış.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `54` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Müşteriden güncel son kullanma tarihini girmesini ya da yeni kart eklemesini isteyin.

## Şema Karşılığı
Visa: 54 · Mastercard: 54. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
