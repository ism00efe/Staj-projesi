# Prosedür: Takas ve Mutabakat Gecikmeleri

Kategori: teknik · Yeniden deneme: Uygulanamaz (manuel inceleme gerektirir)

## Belirti
Kapalı provizyona dönüşmüş (captured) işlemler beklenen zamanda hesap özetinde
görünmüyor.

## Olası Neden
Banka takas dosyası beklenen kesim saatinden geç geldi, ya da Takas Motoru ile banka
kaydı arasında bir mutabakatsızlık var. Bkz. `errorcodes_settlement.md`.

## İnceleme Adımları
1. İşlemlerin gerçekten `captured` durumda olduğunu doğrulayın (sadece `authorized`
   değil).
2. İç kayıt sayısını banka takas dosyasındaki sayıyla karşılaştırın.
3. Fark varsa eksik ya da mükerrer bir batch'e işaret eder; bkz.
   `postmortem_settlement_mismatch.md`.

## Çözüm
Geç gelen dosya: genellikle bir sonraki döngüde tamamlanır, izleyin. Mükerrer batch
şüphesi varsa mutabakatı durdurup finans ekibiyle iletişime geçmeden önce hiçbir kayıt
düzeltmesi yapmayın.
