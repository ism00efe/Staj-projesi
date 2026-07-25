# Olay Sonrası Analiz (Postmortem): Zirve POS Kesintisi

**Özet:** 2026-07-18 tarihinde Zirve POS terminallerinin yaklaşık %30'u 40 dakika boyunca yetkilendirme isteklerine yanıt veremedi.

**Kök Neden:** Kartlı Ödeme Motoru (KÖM)'ne yapılan bir dağıtım (deployment), terminal kimlik doğrulama servisinde bir bağlantı havuzu (connection pool) tükenmesine yol açtı.

**Etki:** Etkilenen üye işyerlerinde işlemler RC-96 ile reddedildi; tahmini kayıp işlem sayısı 1.200 civarındaydı.

**Alınan Aksiyonlar:** Bağlantı havuzu boyutu artırıldı; dağıtım öncesi yük testi süreci zorunlu hale getirildi. Bkz. `runbook_rc96.md`.
