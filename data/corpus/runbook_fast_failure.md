# Prosedür: FAST Transfer Başarısızlığı

Kategori: teknik · Yeniden deneme: Evet (idempotency anahtarıyla)

## Belirti
Havale/Fast Bridge üzerinden gönderilen transferler tamamlanamıyor veya beklenenden çok
daha uzun sürüyor.

## Olası Neden
Alıcı bankanın sistemi geçici olarak yanıt vermiyor, günlük limit aşılmış, ya da
Havale/Fast Bridge'in kendisinde bir kuyruk birikmesi var. Bkz. `errorcodes_fast.md`.

## İnceleme Adımları
1. Hata kodunun `receiver_bank_timeout` mi yoksa `bridge_unavailable` mı olduğunu
   belirleyin.
2. Alıcı banka bazında bir yoğunlaşma olup olmadığını kontrol edin.
3. Sürekli gecikme varsa `postmortem_fast_delay.md` dosyasındaki emsal olaya bakın.

## Çözüm
`receiver_bank_timeout` teknik bir hatadır, aynı işlem referansıyla güvenle tekrar
denenebilir. `account_not_found` ve `daily_limit_exceeded` için tekrar deneme
önerilmez.
