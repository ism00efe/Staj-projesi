# E-Ticaret / Online Ödeme Hata Kodu Grupları

Kart hazır olmayan (card-not-present) online işlemlerde, fiziksel kart kontrollerinin
yerini 3DS/SCA doğrulaması alır:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Kimlik Doğrulama | 3DS hataları | Bkz. `errorcodes_3ds.md` |
| Kart Çıkaran Red | RC-05, RC-51, RC-62 | Yeniden deneme önerilmez |
| Format/Entegrasyon | RC-12, RC-30 | Genellikle üye işyeri entegrasyon hatası |

Online ödeme akışı için bkz. `api_authorization.md` ve `api_3ds_initiate.md`.
