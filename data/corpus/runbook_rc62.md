# Prosedür: RC-62 (Kısıtlı Kart / Restricted Card)

Kategori: kart çıkaran red · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-62` yanıt koduyla reddediyor: kart, kart çıkaran kurum tarafından bu işlem için kısıtlanmış.

## Olası Neden
Yurt dışı kullanım kapalı, coğrafi/işlem tipi kısıtlaması uygulanmış ya da kart kayıp/çalıntı olarak bildirilmiş olabilir.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `62` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Müşteriye kartını çıkaran bankayla iletişime geçip kısıtlamayı kaldırmasını veya başka bir kart denemesini önerin.

## Şema Karşılığı
Visa: 62 · Mastercard: 62. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
