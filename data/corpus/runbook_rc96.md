# Prosedür: RC-96 (Sistem Hatası / System Malfunction)

Kategori: teknik · Yeniden deneme: Evet · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-96` yanıt koduyla reddediyor: işlem, alıcı tarafta beklenmeyen bir sistem hatasıyla sonuçlanıyor.

## Olası Neden
Kart çıkaran kurumda ya da Kartlı Ödeme Motoru (KÖM) içinde geçici bir sistem arızası oluştu; genellikle izole ve kısa sürelidir.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `96` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Aynı STAN ile tekrar deneyin; merchant genelinde artış varsa KÖM durumunu ve son dağıtımları (deployment) kontrol edin.

## Şema Karşılığı
Visa: — · Mastercard: 96. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
