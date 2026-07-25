# Prosedür: RC-12 (Geçersiz İşlem / Invalid Transaction)

Kategori: doğrulama · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-12` yanıt koduyla reddediyor: işlem tipi (processing code, DE3) kart veya terminal tarafından desteklenmiyor.

## Olası Neden
İşlem tipi ile mesaj tipi (MTI) uyuşmuyor, ya da terminal konfigürasyonunda bu işlem tipi için tanım eksik (örn. taksitli işlem desteklenmeyen bir terminalde deneniyor).

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `12` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Terminal konfigürasyonunu ve gönderilen processing code (DE3) değerini kontrol edin; alan tanımları için bkz. `api_authorization.md`.

## Şema Karşılığı
Visa: 12 · Mastercard: 12. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
