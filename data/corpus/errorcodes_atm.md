# ATM Hata Kodu Grupları

ATM işlemleri aynı ISO 8583 tabanlı yetkilendirme akışını kullanır, ancak nakit çekim
işlemlerine özgü ek kontroller içerir:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Bakiye | RC-51 | Günlük çekim limiti de ayrıca kontrol edilir |
| Kart | RC-14, RC-54, RC-62 | ATM'ler kartı fiziksel olarak alıkoyabilir (Mastercard 04 benzeri) |
| Sistem | RC-91, RC-96 | Kart çıkaran kuruma veya BKM switch'ine bağlantı sorunları |

Nakit çekim onaylandıktan (RC-00) sonra ATM'nin fiziksel nakit verme hatası ayrı bir
olay sınıfıdır ve bu katalog kapsamı dışındadır.
