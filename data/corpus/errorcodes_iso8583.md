# ISO 8583 Mesaj ve Yanıt Kodu Kataloğu / ISO 8583 Message & Response Code Catalog

## Mesaj Tipleri (MTI) / Message Types
| MTI | Açıklama (TR) | Description (EN) |
|-----|---------------|-------------------|
| 0100 | Yetkilendirme İsteği | Authorization Request |
| 0110 | Yetkilendirme Yanıtı | Authorization Response |
| 0420 | Ters İbraz İsteği | Reversal Request |
| 0430 | Ters İbraz Yanıtı | Reversal Response |

## Yanıt Kodları (DE39) / Response Codes (DE39)
| Kod | Neden (TR) | Reason (EN) | Kategori | Yeniden Deneme |
|-----|------------|-------------|----------|----------------|
| RC-00 | Onaylandı | Approved | — | — |
| RC-05 | İşlem Reddedildi (Genel Red) | Do Not Honor | kart çıkaran red | Hayır |
| RC-12 | Geçersiz İşlem | Invalid Transaction | doğrulama | Hayır |
| RC-14 | Geçersiz Kart Numarası | Invalid Card Number | doğrulama | Hayır |
| RC-30 | Format Hatası | Format Error | teknik | Evet |
| RC-51 | Yetersiz Bakiye | Insufficient Funds | kart çıkaran red | Hayır |
| RC-54 | Kartın Süresi Dolmuş | Expired Card | doğrulama | Hayır |
| RC-62 | Kısıtlı Kart | Restricted Card | kart çıkaran red | Hayır |
| RC-91 | Kart Çıkaran Kuruma Ulaşılamıyor | Issuer or Switch Inoperative | teknik | Evet |
| RC-96 | Sistem Hatası | System Malfunction | teknik | Evet |

Sadece `teknik` (technical) kategorisindeki kodlar (RC-30, RC-91, RC-96) otomatik
yeniden denemeye güvenlidir, ve yalnızca aynı STAN (DE11) ile. Her kod için detaylı
prosedür `runbook_rc{code}.md` dosyalarında bulunur. Alan tanımları için bkz.
`api_authorization.md`.
