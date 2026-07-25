# Prosedür: RC-51 (Yetersiz Bakiye / Insufficient Funds)

Kategori: kart çıkaran red · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-51` yanıt koduyla reddediyor: kart sahibinin hesabında işlem tutarı kadar bakiye bulunmuyor.

## Olası Neden
Kart sahibinin kullanılabilir bakiyesi talep edilen tutardan düşük; açık provizyonlar (henüz kapatılmamış ön otorizasyonlar) bakiyeyi bloke etmiş olabilir.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `51` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Müşteriye başka bir ödeme yöntemi önerin veya bakiyesini kontrol etmesini isteyin; aynı kartla tekrar deneme önerilmez.

## Şema Karşılığı
Visa: 51 · Mastercard: 51. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
