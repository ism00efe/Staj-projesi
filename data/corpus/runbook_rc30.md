# Prosedür: RC-30 (Format Hatası / Format Error)

Kategori: teknik · Yeniden deneme: Evet · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-30` yanıt koduyla reddediyor: ISO 8583 mesajı reddediliyor, işlem hiç kart çıkaran kuruma ulaşmıyor.

## Olası Neden
Mesajda zorunlu bir alan eksik, yanlış uzunlukta ya da beklenmeyen bir karakter seti içeriyor — genellikle entegrasyon tarafındaki bir sürüm uyuşmazlığından kaynaklanır.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `30` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Mesaj alanlarını (özellikle DE4 tutar ve DE11 STAN uzunluklarını) `errorcodes_iso8583.md` referansına göre doğrulayın; entegrasyon ekibiyle iletişime geçin.

## Şema Karşılığı
Visa: 30 · Mastercard: 30. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
