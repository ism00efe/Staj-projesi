# Prosedür: RC-05 (İşlem Reddedildi (Genel Red) / Do Not Honor)

Kategori: kart çıkaran red · Yeniden deneme: Hayır · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
Kartlı Ödeme Motoru (KÖM) işlemleri `RC-05` yanıt koduyla reddediyor: kart sahibinin bankası işlemi herhangi bir özel gerekçe belirtmeden reddediyor.

## Olası Neden
İşlem, kart çıkaran kurumun risk motoru tarafından spesifik bir neden paylaşılmadan engelleniyor; genellikle banka içi skorlama kurallarının sonucudur ve bizim sistemimizde görünür bir hata yoktur.

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `05` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, Kartlı Ödeme Motoru (KÖM) durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
Müşteriye başka bir kart denemesini veya kartını çıkaran bankayla doğrudan iletişime geçmesini önerin; aynı kartla tekrar deneme sonucu değiştirmez.

## Şema Karşılığı
Visa: 05 · Mastercard: 05. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
