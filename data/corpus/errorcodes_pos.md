# Zirve POS Hata Kodu Grupları

Zirve POS terminal katmanında görülen hatalar, ISO 8583 yanıt kodlarının (bkz.
`errorcodes_iso8583.md`) terminal bağlamına özgü bir alt kümesidir:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Kart Doğrulama | RC-14, RC-54 | Genellikle fiziksel kart kontrolü gerektirir |
| Bağlantı | RC-91, RC-96 | Terminal-Kartlı Ödeme Motoru (KÖM) bağlantısı ile ilgili |
| Kısıtlama | RC-62 | Kart çıkaran kurum kaynaklı |
| Format | RC-30 | Terminal firmware sürümü kontrol edilmeli |

Terminal kurulumu için bkz. `guide_pos_terminal_setup.md`.
