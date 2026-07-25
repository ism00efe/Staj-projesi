# Prosedür: RC-91 (Kart Çıkaran Kuruma Ulaşılamıyor / Issuer or Switch Inoperative)

Kategori: teknik · Yeniden deneme: Evet · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-91` yanıt koduyla reddediyor: yetkilendirme isteği kart çıkaran bankaya ya da BKM switch'ine zaman aşımına uğruyor.

## Olası Neden
Kart çıkaran kurumun sistemi ya da BKM anahtarlama (switch) altyapısı geçici olarak yanıt vermiyor; işlemin gerçek sonucu belirsiz kalabilir.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `91` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Önce işlem durumunu sorgulayın (`api_authorization.md` sorgu ucu), ardından aynı STAN ile tekrar deneyin; süreklilik gösteriyorsa BKM durum sayfasını kontrol edip olay (incident) açın.

## Şema Karşılığı
Visa: 91 · Mastercard: —. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
