# Prosedür: RC-14 (Geçersiz Kart Numarası / Invalid Card Number)

Kategori: doğrulama · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-14` yanıt koduyla reddediyor: kart numarası (PAN) format kontrolünden geçemiyor.

## Olası Neden
PAN Luhn kontrolünden geçemiyor ya da girilen BIN aralığı hiçbir kart çıkaran kuruma tanımlı değil — genellikle elle giriş hatası.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `14` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Müşteriden kart numarasını dikkatlice tekrar girmesini isteyin; kart fiziksel olarak kontrol edilmelidir.

## Şema Karşılığı
Visa: 14 · Mastercard: 14. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
