"""Synthetic dataset generator (v2, realistic bilingual payment-systems corpus).

Full rebuild (Phase 5): the v1 corpus used generic template content (`PAY-1001`,
`com.example.payments.*`) that would not hold up in front of a bank's payment systems
team. v2 replaces it entirely with ~93 documents modeled on real international payment
standards (ISO 8583, ISO 20022/SWIFT, EMV, card-scheme decline codes) and the Turkish
payment ecosystem (BKM, Troy, FAST), bilingual (Turkish + English) to match how a
Turkish bank actually operates: internal runbooks and regulations in Turkish,
international standards and API docs in English.

Content authorship & review (see DECISIONS.md D20 for the full disclosure — documented
once here, not repeated per file, so it never pollutes the embedded/indexed text):
this corpus was authored directly by the assistant, reviewed for factual plausibility
against publicly documented standards while writing (ISO 8583 response code meanings,
EMV terminology, BKM/Troy/FAST descriptions), and contains no real PII — all card/TCKN
values are either well-known published test values or algorithmically valid-but-obviously
synthetic patterns (see `_PII` below).

Fictional entities used throughout, deliberately, so nothing here is attributable to a
real institution: bank = "Vera Bank" (`com.verabank.*` / `tr.com.verabank.*` in code and
package names), merchants = "Marmara Elektronik", "Ege Market", "Anadolu Tekstil".
Real, public infrastructure/standards are referenced by name where accurate: BKM
(Bankalararası Kart Merkezi), Troy, FAST (Fonların Anlık ve Sürekli Transferi), Visa,
Mastercard, ISO 8583, ISO 20022, SWIFT, EMV, PCI DSS — these are standards/schemes, not
fabricated failures attributed to a specific company.

Deterministic and LLM-free at *runtime* (no network/model calls in `generate_corpus`);
some log samples contain fake-but-valid PII so sanitization can be demonstrated end to
end. Filenames use only the 8 prefixes `ingestion.py` already classifies
(`api_ errorcodes_ runbook_ faq_ log_ trace_ concept_ guide_`); the two new content
genres are placed accordingly — configuration guides under `guide_` (a natural fit),
incident postmortems under a new `postmortem_` prefix, which falls through to the
generic `"document"` doc_type (harmless: doc_type is display/citation metadata only,
never used for retrieval).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fictional entities (consistent across the whole corpus)
# ---------------------------------------------------------------------------
BANK = "Vera Bank"
POS_SYSTEM = "Zirve POS"
AUTH_ENGINE = "Kartlı Ödeme Motoru (KÖM)"
FAST_BRIDGE = "Havale/Fast Bridge"
MERCHANT_PORTAL = "Merchant Portal"
PROVISION_SYSTEM = "Provizyon Sistemi"
CLEARING_ENGINE = "Takas Motoru"
MERCHANTS = ["Marmara Elektronik", "Ege Market", "Anadolu Tekstil"]

# ---------------------------------------------------------------------------
# Synthetic PII — reused, proven-valid values (never real). Sprinkled into ~15-20
# files, not every file: realistic production logs are mostly clean.
# ---------------------------------------------------------------------------
_PII = {
    "card_visa": "4111 1111 1111 1111",  # widely published Luhn-valid test PAN
    "card_mc": "5555 5555 5555 4444",  # widely published Luhn-valid test PAN (Mastercard)
    "tckn_a": "10000000146",  # checksum-valid, obviously-patterned (repeating 0s), not real
    "tckn_b": "56789101248",  # checksum-valid, obviously-patterned, not real
    "email_a": "musteri.hizmetleri@example.com",
    "email_b": "ahmet.yilmaz@example.com",
    "phone_a": "+90 532 111 22 33",
    "phone_b": "0555 222 33 44",
    "ip_a": "10.24.6.18",
    "ip_b": "192.168.44.9",
}


# ---------------------------------------------------------------------------
# Family 1 — ISO 8583 response codes: the backbone "confusable" family (R5).
# Card decline is always the surface symptom; only the reason/cause differs —
# exactly the case a bi-encoder blurs and hybrid+rerank must resolve.
# ---------------------------------------------------------------------------
_RC_CODES: list[dict[str, str]] = [
    {
        "code": "05", "reason_tr": "İşlem Reddedildi (Genel Red)", "reason_en": "Do Not Honor",
        "category_tr": "kart çıkaran red", "retry": "Hayır",
        "symptom_tr": "kart sahibinin bankası işlemi herhangi bir özel gerekçe belirtmeden reddediyor",
        "cause_tr": "İşlem, kart çıkaran kurumun risk motoru tarafından spesifik bir neden "
                    "paylaşılmadan engelleniyor; genellikle banka içi skorlama kurallarının "
                    "sonucudur ve bizim sistemimizde görünür bir hata yoktur.",
        "fix_tr": "Müşteriye başka bir kart denemesini veya kartını çıkaran bankayla doğrudan "
                  "iletişime geçmesini önerin; aynı kartla tekrar deneme sonucu değiştirmez.",
        "visa": "05", "mc": "05",
    },
    {
        "code": "12", "reason_tr": "Geçersiz İşlem", "reason_en": "Invalid Transaction",
        "category_tr": "doğrulama", "retry": "Hayır",
        "symptom_tr": "işlem tipi (processing code, DE3) kart veya terminal tarafından desteklenmiyor",
        "cause_tr": "İşlem tipi ile mesaj tipi (MTI) uyuşmuyor, ya da terminal konfigürasyonunda "
                    "bu işlem tipi için tanım eksik (örn. taksitli işlem desteklenmeyen bir "
                    "terminalde deneniyor).",
        "fix_tr": "Terminal konfigürasyonunu ve gönderilen processing code (DE3) değerini "
                  "kontrol edin; alan tanımları için bkz. `api_authorization.md`.",
        "visa": "12", "mc": "12",
    },
    {
        "code": "14", "reason_tr": "Geçersiz Kart Numarası", "reason_en": "Invalid Card Number",
        "category_tr": "doğrulama", "retry": "Hayır",
        "symptom_tr": "kart numarası (PAN) format kontrolünden geçemiyor",
        "cause_tr": "PAN Luhn kontrolünden geçemiyor ya da girilen BIN aralığı hiçbir kart "
                    "çıkaran kuruma tanımlı değil — genellikle elle giriş hatası.",
        "fix_tr": "Müşteriden kart numarasını dikkatlice tekrar girmesini isteyin; kart "
                  "fiziksel olarak kontrol edilmelidir.",
        "visa": "14", "mc": "14",
    },
    {
        "code": "30", "reason_tr": "Format Hatası", "reason_en": "Format Error",
        "category_tr": "teknik", "retry": "Evet",
        "symptom_tr": "ISO 8583 mesajı reddediliyor, işlem hiç kart çıkaran kuruma ulaşmıyor",
        "cause_tr": "Mesajda zorunlu bir alan eksik, yanlış uzunlukta ya da beklenmeyen bir "
                    "karakter seti içeriyor — genellikle entegrasyon tarafındaki bir sürüm "
                    "uyuşmazlığından kaynaklanır.",
        "fix_tr": "Mesaj alanlarını (özellikle DE4 tutar ve DE11 STAN uzunluklarını) "
                  "`errorcodes_iso8583.md` referansına göre doğrulayın; entegrasyon ekibiyle "
                  "iletişime geçin.",
        "visa": "30", "mc": "30",
    },
    {
        "code": "51", "reason_tr": "Yetersiz Bakiye", "reason_en": "Insufficient Funds",
        "category_tr": "kart çıkaran red", "retry": "Hayır",
        "symptom_tr": "kart sahibinin hesabında işlem tutarı kadar bakiye bulunmuyor",
        "cause_tr": "Kart sahibinin kullanılabilir bakiyesi talep edilen tutardan düşük; "
                    "açık provizyonlar (henüz kapatılmamış ön otorizasyonlar) bakiyeyi "
                    "bloke etmiş olabilir.",
        "fix_tr": "Müşteriye başka bir ödeme yöntemi önerin veya bakiyesini kontrol etmesini "
                  "isteyin; aynı kartla tekrar deneme önerilmez.",
        "visa": "51", "mc": "51",
    },
    {
        "code": "54", "reason_tr": "Kartın Süresi Dolmuş", "reason_en": "Expired Card",
        "category_tr": "doğrulama", "retry": "Hayır",
        "symptom_tr": "provizyon anında kartın son kullanma tarihi geçmiş durumda",
        "cause_tr": "Kayıtlı (saklanmış) kartlarda sık görülür: kart süresi dolmuş ama "
                    "hesap güncelleme servisi (account updater) henüz yeni kart bilgisini "
                    "almamış.",
        "fix_tr": "Müşteriden güncel son kullanma tarihini girmesini ya da yeni kart "
                  "eklemesini isteyin.",
        "visa": "54", "mc": "54",
    },
    {
        "code": "62", "reason_tr": "Kısıtlı Kart", "reason_en": "Restricted Card",
        "category_tr": "kart çıkaran red", "retry": "Hayır",
        "symptom_tr": "kart, kart çıkaran kurum tarafından bu işlem için kısıtlanmış",
        "cause_tr": "Yurt dışı kullanım kapalı, coğrafi/işlem tipi kısıtlaması uygulanmış ya "
                    "da kart kayıp/çalıntı olarak bildirilmiş olabilir.",
        "fix_tr": "Müşteriye kartını çıkaran bankayla iletişime geçip kısıtlamayı "
                  "kaldırmasını veya başka bir kart denemesini önerin.",
        "visa": "62", "mc": "62",
    },
    {
        "code": "91", "reason_tr": "Kart Çıkaran Kuruma Ulaşılamıyor",
        "reason_en": "Issuer or Switch Inoperative",
        "category_tr": "teknik", "retry": "Evet",
        "symptom_tr": "yetkilendirme isteği kart çıkaran bankaya ya da BKM switch'ine "
                      "zaman aşımına uğruyor",
        "cause_tr": "Kart çıkaran kurumun sistemi ya da BKM anahtarlama (switch) altyapısı "
                    "geçici olarak yanıt vermiyor; işlemin gerçek sonucu belirsiz kalabilir.",
        "fix_tr": "Önce işlem durumunu sorgulayın (`api_authorization.md` sorgu ucu), "
                  "ardından aynı STAN ile tekrar deneyin; süreklilik gösteriyorsa BKM durum "
                  "sayfasını kontrol edip olay (incident) açın.",
        "visa": "91", "mc": None,
    },
    {
        "code": "96", "reason_tr": "Sistem Hatası", "reason_en": "System Malfunction",
        "category_tr": "teknik", "retry": "Evet",
        "symptom_tr": "işlem, alıcı tarafta beklenmeyen bir sistem hatasıyla sonuçlanıyor",
        "cause_tr": "Kart çıkaran kurumda ya da Kartlı Ödeme Motoru (KÖM) içinde geçici bir "
                    "sistem arızası oluştu; genellikle izole ve kısa sürelidir.",
        "fix_tr": "Aynı STAN ile tekrar deneyin; merchant genelinde artış varsa KÖM "
                  "durumunu ve son dağıtımları (deployment) kontrol edin.",
        "visa": None, "mc": "96",
    },
]

# Card-scheme codes that don't map 1:1 onto our RC catalog — kept for the
# errorcodes_visa_mastercard.md cross-reference (R1).
_SCHEME_ONLY = [
    ("Mastercard", "04", "Pick Up Card", "RC-62 (Kısıtlı Kart)",
     "Kartın el konulması istenir; genellikle kayıp/çalıntı bildirimiyle ilişkilidir."),
    ("Mastercard", "57", "Transaction Not Permitted to Cardholder", "RC-12 / RC-62",
     "Kart sahibi için bu işlem tipi (örn. yurt dışı, taksitli) izinli değil."),
]


def _rrn(index: int) -> str:
    """A plausible 12-character RRN (DE37).

    Real-world RRN formats are processor-defined and commonly alphanumeric (not purely
    numeric) — this both matches that reality and, incidentally, avoids a false-positive
    in the sanitization module's phone-number pattern, which (correctly, conservatively)
    treats any bare 9-14 digit run as a possible phone number. A pure-digit 12-character
    RRN would trigger it; this alphanumeric form does not, without misrepresenting the
    field.
    """

    letter = chr(65 + index % 26)
    return f"260725{letter}{(100000 + index * 233) % 100000:05d}"


def _runbook_for_rc(rc: dict[str, str]) -> tuple[str, str]:
    name = f"runbook_rc{rc['code']}.md"
    scheme_line = f"Visa: {rc['visa'] or '—'} · Mastercard: {rc['mc'] or '—'}"
    body = f"""# Prosedür: RC-{rc['code']} ({rc['reason_tr']} / {rc['reason_en']})

Kategori: {rc['category_tr']} · Yeniden deneme: {rc['retry']} · Yanıt mesajı: MTI 0110
(Yetkilendirme Yanıtı) veya MTI 0430 (Ters İbraz Yanıtı)

## Belirti
{AUTH_ENGINE} işlemleri `RC-{rc['code']}` yanıt koduyla reddediyor: {rc['symptom_tr']}.

## Olası Neden
{rc['cause_tr']}

## İnceleme Adımları
1. İşlemin yanıt kodunun (DE39) tam olarak `{rc['code']}` olduğunu doğrulayın; STAN (DE11)
   ve RRN (DE37) ile ilgili işlemi loglarda bulun.
2. Sorunun tek bir kart/müşteriye mi yoksa üye işyeri genelinde mi olduğunu kontrol edin.
3. Üye işyeri genelinde bir artış varsa, {AUTH_ENGINE} durumunu ve son dağıtımları
   (deployment) kontrol edin; şema karşılıklarını doğrulamak için
   `errorcodes_visa_mastercard.md` dosyasına bakın.

## Çözüm
{rc['fix_tr']}

## Şema Karşılığı
{scheme_line}. Alan tanımları için bkz. `api_authorization.md`; kod kataloğunun tamamı
için bkz. `errorcodes_iso8583.md`.
"""
    return name, body


def _json_log_for_rc(rc: dict[str, str], index: int, *, with_pii: bool) -> tuple[str, str]:
    # transactionId includes a letter (not a pure digit run) deliberately: the card
    # regex tolerates dashes between digits, so an 8-digit date + a pure 5-digit
    # sequence forms a 13-digit span that's occasionally Luhn-valid by chance and gets
    # (correctly, per the regex's own rules) masked as [CARD] — a real false positive
    # this generator hit during authoring. The letter breaks the digit run structurally.
    name = f"log_rc{rc['code']}.json"
    merchant = MERCHANTS[index % len(MERCHANTS)]
    customer_block = ""
    if with_pii:
        customer_block = f""",
  "customer": {{
    "email": "{_PII['email_a'] if index % 2 == 0 else _PII['email_b']}",
    "phone": "{_PII['phone_a'] if index % 2 == 0 else _PII['phone_b']}",
    "tckn": "{_PII['tckn_a'] if index % 2 == 0 else _PII['tckn_b']}"
  }},
  "card": {{ "pan": "{_PII['card_visa'] if index % 2 == 0 else _PII['card_mc']}" }}"""
    body = f"""{{
  "timestamp": "2026-07-25T{9 + index:02d}:{(index * 7) % 60:02d}:{(index * 13) % 60:02d}Z",
  "level": "ERROR",
  "service": "karti-odeme-motoru",
  "event": "payment.declined",
  "transactionId": "TRX-20260725-{chr(65 + index % 26)}{(1000 + index * 37) % 10000:04d}",
  "mti": "0110",
  "processingCode": "000000",
  "stan": "{100000 + index * 91:06d}",
  "rrn": "{_rrn(index)}",
  "responseCode": "{rc['code']}",
  "responseReason": "{rc['reason_en']}",
  "merchant": {{ "id": "MID-{2000 + index}", "name": "{merchant}" }},
  "amount": {1500 + index * 340},
  "currency": "TRY",
  "clientIp": "{_PII['ip_a'] if index % 3 == 0 else _PII['ip_b']}"{customer_block},
  "message": "{rc['reason_en']} - see runbook_rc{rc['code']}.md"
}}
"""
    return name, body


def _xml_log_for_rc(rc: dict[str, str], index: int, *, with_pii: bool) -> tuple[str, str]:
    name = f"log_rc{rc['code']}.xml"
    pii_block = ""
    if with_pii:
        pii_block = f"""
  <customerEmail>{_PII['email_a']}</customerEmail>
  <customerPhone>{_PII['phone_a']}</customerPhone>"""
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<iso8583Message>
  <mti>0110</mti>
  <de3 name="processingCode">000000</de3>
  <de4 name="amount">{1200 + index * 415}</de4>
  <de11 name="stan">{200000 + index * 71:06d}</de11>
  <de37 name="rrn">{_rrn(index + 50)}</de37>
  <de39 name="responseCode">{rc['code']}</de39>
  <de41 name="terminalId">TRM{3000 + index}</de41>
  <de42 name="merchantId">MID-{4000 + index}</de42>
  <message>{rc['reason_en']} / {rc['reason_tr']}</message>{pii_block}
</iso8583Message>
"""
    return name, body


# ---------------------------------------------------------------------------
# Family 2 — API reference (EN)
# ---------------------------------------------------------------------------
_API_ENDPOINTS: list[tuple[str, str, str, str]] = [
    ("authorization", "POST /v1/authorizations",
     "submit an ISO 8583-style authorization request (equivalent to an MTI 0100)",
     "Fields mirror ISO 8583 data elements: `pan` (DE2, tokenized), `processing_code` "
     "(DE3), `amount` (DE4), `stan` (DE11, caller-generated), `merchant_id` (DE42), "
     "`terminal_id` (DE41). The response includes `response_code` (DE39) — see "
     "`errorcodes_iso8583.md` for the full code table."),
    ("capture", "POST /v1/captures",
     "capture (settle) a previously authorized transaction",
     "Requires `authorization_id`. Only transactions in `authorized` state can be "
     "captured, and only once — a second capture returns RC-12 (`Invalid Transaction`)."),
    ("reversal", "POST /v1/reversals",
     "reverse (void) an authorization before it settles, equivalent to an ISO 8583 "
     "MTI 0420 request",
     "Requires the original `stan` and `rrn`. A reversal releases the held funds "
     "without a capture; once a transaction has settled, use `api_refund.md` instead."),
    ("refund", "POST /v1/refunds",
     "refund a captured (settled) transaction",
     "Requires `transaction_id` and `amount`. Partial refunds are allowed up to the "
     "captured total. Refund settlement follows the standard takas (clearing) cycle, "
     "typically 1-3 business days."),
    ("settlement_inquiry", "GET /v1/settlements/{batch_id}",
     "query the status of a settlement (takas) batch",
     "Returns per-transaction reconciliation status against the acquirer file. See "
     "`concept_pos_atm_flow.md` for how authorization, capture, and settlement relate."),
    ("tokenization", "POST /v1/tokens",
     "exchange a raw PAN for a reusable token",
     "The raw PAN never touches merchant systems after tokenization, keeping merchants "
     "out of PCI DSS scope for card storage — see `concept_pci_scope.md`."),
    ("3ds_initiate", "POST /v1/3ds/initiate",
     "start a 3-D Secure / SCA (Strong Customer Authentication) challenge",
     "Required for most card-not-present transactions under current SCA rules. On "
     "completion the issuer's ACS returns a cryptographic result consumed by the "
     "authorization call. See `errorcodes_3ds.md` and `guide_3ds_enrollment.md`."),
    ("openbanking_payment", "POST /v1/openbanking/payment-orders",
     "initiate an open banking payment order (ödeme emri) on behalf of a customer",
     "Requires explicit customer consent (`consent_id`) obtained via the open banking "
     "consent flow. See `errorcodes_openbanking.md` for consent- and IBAN-related "
     "failures."),
    ("qr_payment", "POST /v1/qr-payments",
     "generate or redeem a QR code payment",
     "Static or dynamic QR codes encode a `merchant_id` and optional fixed `amount`; "
     "redemption follows the same authorization path as a card-present transaction."),
    ("recurring_billing", "POST /v1/subscriptions",
     "charge a tokenized card on a recurring schedule",
     "Recurring (merchant-initiated) transactions are generally exempt from a fresh "
     "3DS challenge under card-scheme rules, provided the initial charge was "
     "customer-initiated and challenged."),
]


# ---------------------------------------------------------------------------
# Family 3 — FAQ (6 TR, 4 EN)
# ---------------------------------------------------------------------------
_FAQ_TOPICS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    ("provizyon", "Provizyon Süreçleri", "tr", [
        ("Açık provizyon ile kapalı provizyon arasındaki fark nedir?",
         "Açık provizyon, tutarın kart sahibinin hesabında bloke edilip henüz tahsil "
         "edilmediği durumdur (authorization). Kapalı provizyon ise tutarın fiilen "
         "tahsil edildiği (capture) durumdur. Bkz. `api_capture.md`."),
        ("Açık provizyon ne kadar süre bekletilebilir?",
         "Şemaya göre değişir; genellikle 7 gün içinde kapatılmayan (capture "
         "edilmeyen) açık provizyonlar otomatik olarak düşer."),
        ("Provizyon RC-91 ile reddedilirse ne yapmalıyım?",
         "Önce işlem durumunu sorgulayın, ardından aynı STAN ile tekrar deneyin. "
         "Bkz. `runbook_rc91.md`."),
    ]),
    ("ters_ibraz", "Ters İbraz (Chargeback) Süreci", "tr", [
        ("Ters ibraz nedir?", "Kart sahibinin bankası tarafından başlatılan, işlemin "
         "zorla geri alınmasıdır (MTI 0420/0430 akışına benzer ama şema seviyesinde "
         "yürütülür). Üye işyeri kanıt sunma süresi içinde itiraz edebilir."),
        ("Ters ibraza itiraz süresi ne kadardır?",
         "Şemaya göre değişir, genellikle bildirimden itibaren 7-20 gün arasındadır."),
        ("Ters ibraz kaybedilirse ne olur?", "Tutar kart sahibine iade edilir ve sabit "
         "bir itiraz ücreti üye işyerine yansıtılır."),
    ]),
    ("uye_isyeri_onboarding", "Üye İşyeri Onboarding", "tr", [
        ("Yeni bir üye işyeri nasıl tanımlanır?",
         "Bkz. `guide_merchant_onboarding.md` — MCC (üye işyeri kategori kodu), "
         "yerleşim ve limit tanımları gerekir."),
        ("Üye işyeri limitleri neye göre belirlenir?",
         "Sektör (MCC), beklenen işlem hacmi ve risk değerlendirmesine göre "
         "Provizyon Sistemi üzerinden tanımlanır."),
        ("Bir üye işyeri Merchant Portal'a nasıl erişir?",
         "Onboarding tamamlandıktan sonra API anahtarları Merchant Portal üzerinden "
         "tanımlanır; bkz. `guide_api_key_rotation.md`."),
    ]),
    ("takas", "Takas ve Mutabakat", "tr", [
        ("Takas (settlement) ne zaman gerçekleşir?",
         "Kapalı provizyonlar, günlük kesim saatine göre gruplanıp Takas Motoru "
         "tarafından toplu olarak bankaya iletilir."),
        ("Hesap özetinde eksik işlem görürsem ne yapmalıyım?",
         "Önce işlemin gerçekten kapalı provizyona (capture) dönüştüğünü doğrulayın; "
         "bkz. `runbook_settlement_delay.md`."),
        ("Mutabakat farkı nasıl araştırılır?",
         "İç kayıtlar, banka takas dosyasıyla satır satır karşılaştırılır; fark "
         "eksik veya mükerrer bir batch'e işaret eder."),
    ]),
    ("troy", "Troy Kart Şeması", "tr", [
        ("Troy nedir?", "BKM öncülüğünde geliştirilen, yerli banka/kredi kartı "
         "şemasıdır; yurt içi işlemlerde uluslararası şemalara alternatif sunar."),
        ("Troy işlemleri farklı bir onay akışından mı geçer?",
         "Hayır, aynı ISO 8583 tabanlı yetkilendirme akışını kullanır; şema "
         "kimliği DE alanlarından biriyle ayırt edilir."),
        ("Troy ile uluslararası işlem yapılabilir mi?",
         "Troy'un kapsamı öncelikli olarak yurt içidir; yurt dışı kabul, şemanın "
         "ilgili ortaklıklarına bağlıdır."),
    ]),
    ("fast", "FAST Ödemeleri", "tr", [
        ("FAST nedir?", "Fonların Anlık ve Sürekli Transferi — bankalar arası anlık "
         "para transferi sistemidir, 7/24 çalışır."),
        ("FAST işlemi neden gecikir?", "Bkz. `runbook_fast_failure.md` — alıcı "
         "bankanın sistemine ulaşılamaması en sık nedendir."),
        ("FAST limiti var mı?", "Evet, işlem başına ve günlük olmak üzere BKM "
         "tarafından belirlenen üst limitler uygulanır."),
    ]),
    ("3ds", "3-D Secure", "en", [
        ("When is a 3DS challenge required?",
         "Whenever regulation mandates Strong Customer Authentication (SCA) for the "
         "transaction — most card-not-present payments above a low-value threshold."),
        ("Why did the challenge time out?",
         "A slow or unreachable ACS (Access Control Server); see `errorcodes_3ds.md` "
         "and `runbook_3ds_failure.md`."),
        ("Are recurring charges challenged every time?",
         "Usually not — merchant-initiated recurring transactions can qualify for an "
         "SCA exemption if the initial charge was customer-initiated and challenged."),
    ]),
    ("api_integration", "API Integration", "en", [
        ("Do I need to send a STAN on every authorization?",
         "Yes — the System Trace Audit Number (DE11) must be unique per request and "
         "is required to safely retry or reverse a transaction."),
        ("How do I paginate list endpoints?",
         "Cursor pagination via the `starting_after` query parameter."),
        ("What happens on a network timeout mid-authorization?",
         "The transaction state is uncertain — always query status via "
         "`api_authorization.md` before retrying; see `runbook_rc91.md`."),
    ]),
    ("refunds", "Refunds", "en", [
        ("How long does a refund take to settle?",
         "1-3 business days, following the standard clearing (takas) cycle."),
        ("Can I refund more than the captured amount?",
         "No — that fails with an `Invalid Transaction` style rejection; see "
         "`api_refund.md`."),
        ("Can an authorization-only transaction be refunded?",
         "No — void it with `api_reversal.md` instead; refunds require a captured "
         "transaction."),
    ]),
    ("testing_sandbox", "Testing and Sandbox", "en", [
        ("Which test card triggers a decline?",
         "Sandbox PANs are mapped to specific response codes for testing — see "
         "`errorcodes_iso8583.md` for the code table your test card should trigger."),
        ("Does the sandbox settle transactions?",
         "No — settlement is simulated on an accelerated clock, not a real clearing "
         "cycle."),
        ("Can I simulate an issuer timeout?",
         "Yes, the sandbox exposes a trigger amount that returns RC-91."),
    ]),
]


# ---------------------------------------------------------------------------
# Family 4 — conceptual overviews (3 TR, 5 EN)
# ---------------------------------------------------------------------------
_CONCEPTS: list[tuple[str, str, str, str]] = [
    ("bkm", "BKM (Bankalararası Kart Merkezi)", "tr",
     "BKM, Türkiye'deki bankalar arası kartlı ödeme sisteminin işletilmesinden sorumlu "
     "kuruluştur; anahtarlama (switching), takas ve ortak altyapı hizmetlerini sağlar. "
     f"{BANK} gibi kart çıkaran ve üye işyeri anlaşması yapan kurumlar, yurt içi "
     "işlemlerde BKM altyapısı üzerinden anahtarlanır. Troy şeması da BKM öncülüğünde "
     "geliştirilmiştir."),
    ("troy", "Troy Kart Şeması", "tr",
     "Troy, BKM öncülüğünde geliştirilen yerli banka/kredi kartı şemasıdır. Uluslararası "
     "şemalarla aynı ISO 8583 tabanlı yetkilendirme akışını kullanır; şema seviyesindeki "
     "fark, işlem yönlendirme ve ücretlendirme kurallarındadır. Detaylı sorular için "
     "bkz. `faq_troy.md`."),
    ("fast_payments", "FAST (Fonların Anlık ve Sürekli Transferi)", "tr",
     "FAST, bankalar arası anlık para transferi sistemidir ve 7 gün 24 saat kesintisiz "
     "çalışır. Kart işlemlerinden farklı olarak ISO 8583 değil, banka hesapları arası "
     "doğrudan transfer akışını kullanır. Hata durumları için bkz. "
     "`errorcodes_fast.md` ve `runbook_fast_failure.md`."),
    ("pos_atm_flow", "POS / ATM Transaction Lifecycle", "en",
     "A card-present transaction moves through four stages: **authorization** (an "
     "ISO 8583 MTI 0100 request holds funds), **capture** (the merchant settles the "
     "authorized amount, converting it to a receivable), **settlement** (captured "
     "transactions clear in a batch, moving funds from acquirer to merchant), and "
     "**chargeback** (the cardholder's issuer can still force a reversal after "
     "settlement, within the scheme's dispute window). See `api_authorization.md`, "
     "`api_capture.md`, and `faq_ters_ibraz.md`."),
    ("iso8583_overview", "ISO 8583 Message Structure", "en",
     "ISO 8583 defines the message format most card networks use for financial "
     "transactions. Message Type Indicators (MTIs) identify the message's purpose: "
     "`0100` (authorization request), `0110` (authorization response), `0420` "
     "(reversal request), `0430` (reversal response). Each message carries a set of "
     "Data Elements (DEs) — e.g. DE2 (PAN), DE3 (processing code), DE4 (amount), DE11 "
     "(STAN), DE37 (RRN), DE39 (response code). See `errorcodes_iso8583.md` for the "
     "full response code table used across this system."),
    ("iso20022_swift", "ISO 20022 / SWIFT Messaging", "en",
     "ISO 20022 is the XML-based messaging standard increasingly replacing older "
     "SWIFT MT formats for cross-border and interbank payments. Key message types: "
     "`pacs.008` (FI-to-FI customer credit transfer), `pacs.002` (payment status "
     "report), `camt.053` (bank-to-customer statement), `camt.056` (payment "
     "cancellation request). Unlike ISO 8583's compact binary-ish fields, ISO 20022 "
     "messages are structured, self-describing XML, better suited to cross-border "
     "compliance data."),
    ("tokenization", "Tokenization", "en",
     "Tokenization replaces a card number (PAN) with a surrogate value usable only by "
     "the merchant it was issued to. The raw PAN never touches merchant systems after "
     "the initial exchange, which is what keeps most merchants out of full PCI DSS "
     "scope for storage. Tokens survive card expiry through account-updater services "
     "and underpin saved-card and recurring-billing flows. See `api_tokenization.md`."),
    ("pci_scope", "PCI DSS Scope", "en",
     "Any system that stores, processes, or transmits raw card data falls within PCI "
     "DSS scope. Tokenization (see `concept_tokenization.md`) shrinks scope by keeping "
     "the PAN out of merchant and, where possible, internal systems. Logs must never "
     "contain a full PAN — masking is mandatory before storage, which is exactly what "
     "this system's sanitization layer enforces before anything reaches the "
     "knowledge base or an LLM prompt."),
]


# ---------------------------------------------------------------------------
# Family 5 — configuration guides (4 TR, 1 EN)
# ---------------------------------------------------------------------------
_GUIDES: list[tuple[str, str, str, str]] = [
    ("pos_terminal_setup", f"{POS_SYSTEM} Terminal Kurulumu", "tr",
     f"Yeni bir {POS_SYSTEM} terminali kurulumu için: (1) terminal seri numarasını "
     "Merchant Portal üzerinden üye işyeri hesabına tanımlayın, (2) terminal kimliğini "
     "(DE41) ve üye işyeri kimliğini (DE42) girin, (3) test işlemiyle bağlantıyı "
     f"doğrulayın. Alan tanımları için bkz. `api_authorization.md`."),
    ("merchant_onboarding", "Üye İşyeri Onboarding Rehberi", "tr",
     "Yeni üye işyeri tanımlama adımları: (1) MCC (üye işyeri kategori kodu) ve "
     "beklenen aylık hacmi belirleyin, (2) Provizyon Sistemi üzerinden risk "
     "değerlendirmesi tamamlayın, (3) işlem limitlerini tanımlayın, (4) Merchant "
     "Portal erişimini ve API anahtarını oluşturun — bkz. `guide_api_key_rotation.md`. "
     "Sık sorulan sorular için `faq_uye_isyeri_onboarding.md` dosyasına bakın."),
    ("webhook_setup", "Webhook Kurulumu", "tr",
     "Ödeme olaylarını (authorization, capture, refund) almak için: (1) Merchant "
     "Portal'dan bir webhook uç noktası (endpoint) tanımlayın, (2) paylaşılan gizli "
     "anahtarla (secret) gelen isteklerin imzasını doğrulayın, (3) uç noktanızın hızlı "
     "bir şekilde HTTP 200 döndürdüğünden emin olun — yavaş yanıtlar birikmeye "
     "(backlog) yol açar, bkz. `postmortem_webhook_backlog.md`."),
    ("3ds_enrollment", "3-D Secure Kayıt Rehberi", "tr",
     "Üye işyerini 3DS akışına dahil etmek için: (1) 3DS sağlayıcı entegrasyonunu "
     "Merchant Portal üzerinden etkinleştirin, (2) `api_3ds_initiate.md` uç noktasını "
     "ödeme akışınıza ekleyin, (3) sandbox ortamında zorlu (challenge) senaryosunu "
     "test edin. Hata kodları için bkz. `errorcodes_3ds.md`."),
    ("api_key_rotation", "API Key Rotation", "en",
     "Rotate merchant API keys every 90 days or immediately after a suspected leak: "
     "(1) generate a new key pair in Merchant Portal, (2) deploy the new key to your "
     "integration alongside the old one, (3) confirm traffic on the new key, (4) "
     "revoke the old key. Never share a live key outside your own backend — client-side "
     "code should only ever see a tokenization-scoped key (`api_tokenization.md`)."),
]


# ---------------------------------------------------------------------------
# Family 6 — incident postmortems (TR)
# ---------------------------------------------------------------------------
_POSTMORTEMS: list[tuple[str, str, str]] = [
    ("pos_outage", f"{POS_SYSTEM} Kesintisi",
     f"**Özet:** 2026-07-18 tarihinde {POS_SYSTEM} terminallerinin yaklaşık %30'u "
     "40 dakika boyunca yetkilendirme isteklerine yanıt veremedi.\n\n"
     f"**Kök Neden:** {AUTH_ENGINE}'ne yapılan bir dağıtım (deployment), terminal "
     "kimlik doğrulama servisinde bir bağlantı havuzu (connection pool) tükenmesine "
     "yol açtı.\n\n"
     "**Etki:** Etkilenen üye işyerlerinde işlemler RC-96 ile reddedildi; tahmini "
     "kayıp işlem sayısı 1.200 civarındaydı.\n\n"
     "**Alınan Aksiyonlar:** Bağlantı havuzu boyutu artırıldı; dağıtım öncesi yük "
     "testi süreci zorunlu hale getirildi. Bkz. `runbook_rc96.md`."),
    ("settlement_mismatch", "Takas Mutabakatsızlığı",
     f"**Özet:** 2026-07-10 takas döngüsünde Takas Motoru'nun ürettiği toplam tutar, "
     "banka takas dosyasıyla ~%2 oranında uyuşmadı.\n\n"
     "**Kök Neden:** Aynı batch iki kez işlenmiş (mükerrer gönderim), önceki bir "
     "yeniden deneme (retry) mekanizmasının idempotency kontrolü atlaması "
     "nedeniyle.\n\n"
     "**Etki:** Mutabakat 6 saat gecikti; finansal düzeltme manuel yapıldı.\n\n"
     "**Alınan Aksiyonlar:** Batch gönderimine idempotency anahtarı eklendi. Bkz. "
     "`runbook_settlement_delay.md`."),
    ("3ds_provider_outage", "3DS Sağlayıcı Kesintisi",
     "**Özet:** 2026-06-29 tarihinde harici 3DS sağlayıcısının ACS servisi 25 dakika "
     "boyunca yanıt vermedi.\n\n"
     "**Kök Neden:** Sağlayıcı tarafında bölgesel bir altyapı sorunu (bizim "
     "sistemimizde bir hata tespit edilmedi).\n\n"
     "**Etki:** Kart hazır olmayan (card-not-present) işlemlerin çoğu RC-91 benzeri "
     "bir zaman aşımıyla başarısız oldu.\n\n"
     "**Alınan Aksiyonlar:** İkincil bir 3DS sağlayıcısına otomatik geçiş (failover) "
     "mekanizması eklendi. Bkz. `runbook_3ds_failure.md`."),
    ("fast_delay", "FAST Transfer Gecikmesi",
     f"**Özet:** 2026-06-15 tarihinde {FAST_BRIDGE} üzerinden gönderilen transferlerin "
     "bir kısmı 10 dakikadan fazla gecikti (FAST'in beklenen anlık yanıt süresinin "
     "çok üzerinde).\n\n"
     "**Kök Neden:** Alıcı taraftaki bir bankanın sistemi geçici olarak yavaş yanıt "
     "verdi; bizim tarafımızda kuyruk (queue) birikmesi oluştu.\n\n"
     "**Etki:** ~800 transfer gecikmeli tamamlandı, hiçbiri kaybolmadı.\n\n"
     "**Alınan Aksiyonlar:** Kuyruk için ayrı bir zaman aşımı ve uyarı eşiği "
     "tanımlandı. Bkz. `runbook_fast_failure.md`."),
    ("webhook_backlog", "Webhook Teslimat Birikmesi",
     "**Özet:** 2026-06-02 tarihinde bir üye işyerinin webhook uç noktası yavaş yanıt "
     "vermeye başladı, bu da teslimat kuyruğunda birikmeye yol açtı.\n\n"
     "**Kök Neden:** Üye işyeri entegrasyonu webhook isteğini senkron olarak işliyordu; "
     "kendi sistemlerindeki bir yavaşlama bizim yeniden deneme (retry) mekanizmamızı "
     "tetikledi.\n\n"
     "**Etki:** Bazı `payment.captured` olayları 3 saate kadar gecikmeli iletildi.\n\n"
     "**Alınan Aksiyonlar:** Üye işyerine hızlı HTTP 200 dönüp işlemi asenkron "
     "yapması önerildi; bkz. `guide_webhook_setup.md`."),
]


# ---------------------------------------------------------------------------
# Family 7 — stack traces (EN, fictional package names)
# ---------------------------------------------------------------------------
_TRACES: list[tuple[str, str, str, str, bool]] = [
    ("provizyon_npe", "java.lang.NullPointerException",
     'Cannot invoke "IssuerClient.authorize(AuthRequest)" because "this.issuerClient" is null',
     "com.verabank.odeme.motoru.KartProvizyon.authorize(KartProvizyon.java:112)", False),
    ("gateway_timeout", "java.net.SocketTimeoutException", "Read timed out",
     "com.verabank.odeme.motoru.service.IssuerGatewayClient.send(IssuerGatewayClient.java:88)", False),
    ("webhook_json_parse", "com.fasterxml.jackson.core.JsonParseException",
     "Unexpected character ('<' (code 60))",
     "com.verabank.merchantportal.webhook.WebhookParser.parse(WebhookParser.java:54)", False),
    ("ledger_deadlock", "org.postgresql.util.PSQLException",
     "deadlock detected during ledger update",
     "com.verabank.takas.motoru.LedgerWriter.commit(LedgerWriter.java:201)", False),
    ("signature_mismatch", "java.security.SignatureException",
     "HMAC mismatch on webhook payload",
     "com.verabank.merchantportal.webhook.SignatureVerifier.verify(SignatureVerifier.java:41)", False),
    ("token_resolver", "java.lang.IllegalStateException",
     "card token was null for saved-card charge",
     "com.verabank.odeme.motoru.TokenResolver.resolve(TokenResolver.java:76)", True),
    ("iso8583_parse", "tr.com.verabank.iso8583.MessageParseException",
     "DE4 (amount) field length mismatch: expected 12, got 10",
     "tr.com.verabank.iso8583.Iso8583Parser.parseField(Iso8583Parser.java:133)", False),
    ("fast_timeout", "java.util.concurrent.TimeoutException",
     "FAST bridge did not acknowledge within 5000ms",
     "com.verabank.havale.fastbridge.FastTransferClient.send(FastTransferClient.java:97)", True),
]


def _trace_body(exc: str, message: str, frame: str, component: str, *, with_pii: bool) -> str:
    context = f"component={component}, attempt=2"
    if with_pii:
        context += f", customerEmail={_PII['email_b']}, customerPhone={_PII['phone_b']}"
    return (
        f"ERROR 2026-07-25T14:05:00Z [{AUTH_ENGINE.split()[0].lower()}-worker] "
        "Unhandled exception\n"
        f"{exc}: {message}\n"
        f"    at {frame}\n"
        "    at com.verabank.odeme.motoru.Dispatcher.dispatch(Dispatcher.java:71)\n"
        "    at java.base/java.lang.Thread.run(Thread.java:1583)\n"
        f"Context: {context}\n"
    )


# ---------------------------------------------------------------------------
# Family 8 — hand-written error-code catalogs (10 docs, ~half TR / half EN)
# ---------------------------------------------------------------------------
def _errorcode_catalogs() -> dict[str, str]:
    rc_rows_tr = "\n".join(
        f"| RC-{rc['code']} | {rc['reason_tr']} | {rc['reason_en']} | {rc['category_tr']} | "
        f"{rc['retry']} |"
        for rc in _RC_CODES
    )
    catalogs: dict[str, str] = {}

    catalogs["errorcodes_iso8583.md"] = f"""# ISO 8583 Mesaj ve Yanıt Kodu Kataloğu / ISO 8583 Message & Response Code Catalog

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
{rc_rows_tr}

Sadece `teknik` (technical) kategorisindeki kodlar (RC-30, RC-91, RC-96) otomatik
yeniden denemeye güvenlidir, ve yalnızca aynı STAN (DE11) ile. Her kod için detaylı
prosedür `runbook_rc{{code}}.md` dosyalarında bulunur. Alan tanımları için bkz.
`api_authorization.md`.
"""

    catalogs["errorcodes_visa_mastercard.md"] = f"""# Card Scheme Decline Code Cross-Reference

Card schemes publish their own decline codes, which our system maps onto the internal
RC catalog (`errorcodes_iso8583.md`) at the gateway layer.

| Scheme | Code | Scheme Reason | Internal Equivalent |
|--------|------|----------------|----------------------|
| Visa | 05 | Do Not Honor | RC-05 |
| Visa | 14 | Invalid Account Number | RC-14 |
| Visa | 51 | Insufficient Funds | RC-51 |
| Visa | 54 | Expired Card | RC-54 |
| Visa | 62 | Restricted Card | RC-62 |
| Mastercard | 04 | Pick Up Card | {_SCHEME_ONLY[0][3]} |
| Mastercard | 05 | Do Not Honor | RC-05 |
| Mastercard | 51 | Insufficient Funds | RC-51 |
| Mastercard | 54 | Expired Card | RC-54 |
| Mastercard | 57 | Transaction Not Permitted to Cardholder | {_SCHEME_ONLY[1][3]} |
| Mastercard | 62 | Restricted Card | RC-62 |

Notes:
- Mastercard {_SCHEME_ONLY[0][1]} ({_SCHEME_ONLY[0][2]}): {_SCHEME_ONLY[0][4]}
- Mastercard {_SCHEME_ONLY[1][1]} ({_SCHEME_ONLY[1][2]}): {_SCHEME_ONLY[1][4]}

The mapping is not always 1:1 — some scheme codes (e.g. Mastercard 04) fold into a
broader internal category. See `runbook_rc62.md` for the restricted-card triage flow.
"""

    catalogs["errorcodes_emv.md"] = """# EMV Chip Error Catalog

EMV chip transactions add cryptographic verification beyond the magstripe-era ISO 8583
flow. Common failure classes:

| Error | Meaning | Typical Cause |
|-------|---------|----------------|
| ARQC failure | The chip's Authorization Request Cryptogram doesn't validate against what the issuer expects | Corrupted chip, cloned/counterfeit card, or a card applet bug |
| Cryptogram mismatch | The issuer's host verification of the cryptogram fails during online authorization | Clock skew between terminal and issuer host, or a key management issue |
| TVR anomaly | Terminal Verification Results bitmap flags a risk condition (e.g. "offline PIN not performed", "card on exception file") | Terminal risk-management configuration, or a genuinely risky card/terminal combination |

ARQC and cryptogram failures should never be silently retried — they can indicate a
compromised card. See `runbook_arqc_failure.md` and `runbook_cryptogram_mismatch.md`.
"""

    catalogs["errorcodes_3ds.md"] = """# 3-D Secure / SCA Error Catalog

| Error | Meaning | Retry? |
|-------|---------|--------|
| challenge_timeout | The ACS did not return a challenge result within the timeout window | Maybe — retry the challenge once |
| challenge_abandoned | The cardholder closed the challenge window without completing it | No — ask the cardholder to try again |
| acs_unavailable | The issuer's ACS could not be reached | Yes — treat like RC-91 |
| authentication_failed | The cardholder failed the challenge (wrong OTP, etc.) | No |

See `api_3ds_initiate.md` for the request flow and `runbook_3ds_failure.md` for triage.
"""

    catalogs["errorcodes_pos.md"] = f"""# {POS_SYSTEM} Hata Kodu Grupları

{POS_SYSTEM} terminal katmanında görülen hatalar, ISO 8583 yanıt kodlarının (bkz.
`errorcodes_iso8583.md`) terminal bağlamına özgü bir alt kümesidir:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Kart Doğrulama | RC-14, RC-54 | Genellikle fiziksel kart kontrolü gerektirir |
| Bağlantı | RC-91, RC-96 | Terminal-{AUTH_ENGINE} bağlantısı ile ilgili |
| Kısıtlama | RC-62 | Kart çıkaran kurum kaynaklı |
| Format | RC-30 | Terminal firmware sürümü kontrol edilmeli |

Terminal kurulumu için bkz. `guide_pos_terminal_setup.md`.
"""

    catalogs["errorcodes_atm.md"] = """# ATM Hata Kodu Grupları

ATM işlemleri aynı ISO 8583 tabanlı yetkilendirme akışını kullanır, ancak nakit çekim
işlemlerine özgü ek kontroller içerir:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Bakiye | RC-51 | Günlük çekim limiti de ayrıca kontrol edilir |
| Kart | RC-14, RC-54, RC-62 | ATM'ler kartı fiziksel olarak alıkoyabilir (Mastercard 04 benzeri) |
| Sistem | RC-91, RC-96 | Kart çıkaran kuruma veya BKM switch'ine bağlantı sorunları |

Nakit çekim onaylandıktan (RC-00) sonra ATM'nin fiziksel nakit verme hatası ayrı bir
olay sınıfıdır ve bu katalog kapsamı dışındadır.
"""

    catalogs["errorcodes_online.md"] = """# E-Ticaret / Online Ödeme Hata Kodu Grupları

Kart hazır olmayan (card-not-present) online işlemlerde, fiziksel kart kontrollerinin
yerini 3DS/SCA doğrulaması alır:

| Grup | İlgili RC Kodları | Not |
|------|--------------------|-----|
| Kimlik Doğrulama | 3DS hataları | Bkz. `errorcodes_3ds.md` |
| Kart Çıkaran Red | RC-05, RC-51, RC-62 | Yeniden deneme önerilmez |
| Format/Entegrasyon | RC-12, RC-30 | Genellikle üye işyeri entegrasyon hatası |

Online ödeme akışı için bkz. `api_authorization.md` ve `api_3ds_initiate.md`.
"""

    catalogs["errorcodes_openbanking.md"] = """# Açık Bankacılık (Open Banking) Hata Kodları / Open Banking Error Codes

| Kod / Code | Anlam (TR) | Meaning (EN) |
|------------|------------|----------------|
| consent_expired | Müşteri onayının (consent) süresi dolmuş | Customer consent has expired |
| consent_revoked | Müşteri onayı geri çekilmiş | Customer revoked consent |
| account_not_found | Belirtilen hesap bulunamadı | Specified account not found |
| insufficient_funds | Hesapta yeterli bakiye yok | Account balance insufficient |

Açık bankacılık ödemeleri kart şeması akışını kullanmaz; doğrudan hesaptan hesaba
transferdir. Bkz. `api_openbanking_payment.md`.
"""

    catalogs["errorcodes_settlement.md"] = """# Takas ve Mutabakat Hata Kodları

| Kod | Anlam | Aksiyon |
|-----|-------|---------|
| batch_missing | Beklenen takas dosyası bankadan gelmedi | Bankadan dosyayı yeniden talep edin |
| batch_duplicate | Aynı batch iki kez işlenmiş | Mutabakatı durdurup finans ekibini bilgilendirin |
| amount_mismatch | İç kayıt ile banka dosyası tutarları uyuşmuyor | Satır satır karşılaştırma yapın |

Detaylı inceleme için bkz. `runbook_settlement_delay.md` ve
`postmortem_settlement_mismatch.md`.
"""

    catalogs["errorcodes_fast.md"] = """# FAST Hata Kodları

| Kod | Anlam | Yeniden Deneme |
|-----|-------|-----------------|
| receiver_bank_timeout | Alıcı bankanın sistemi zaman aşımına uğradı | Evet |
| account_not_found | Alıcı hesap/IBAN bulunamadı | Hayır |
| daily_limit_exceeded | Günlük FAST limiti aşıldı | Hayır |
| bridge_unavailable | Havale/Fast Bridge geçici olarak kullanılamıyor | Evet |

Bkz. `runbook_fast_failure.md` ve `concept_fast_payments.md`.
"""

    return catalogs


# ---------------------------------------------------------------------------
# Family 9 — extra logs beyond the RC-driven set (FAST, open banking, SOAP)
# ---------------------------------------------------------------------------
def _extra_logs() -> dict[str, str]:
    logs: dict[str, str] = {}

    logs["log_approved_pos.json"] = f"""{{
  "timestamp": "2026-07-25T10:12:04Z",
  "level": "INFO",
  "service": "karti-odeme-motoru",
  "event": "payment.approved",
  "transactionId": "TRX-20260725-88213",
  "mti": "0110",
  "responseCode": "00",
  "responseReason": "Approved",
  "stan": "441207",
  "rrn": "{_rrn(100)}",
  "merchant": {{ "id": "MID-2001", "name": "Marmara Elektronik" }},
  "amount": 24990,
  "currency": "TRY",
  "message": "Approved - see api_authorization.md"
}}
"""

    logs["log_approved_ecom.json"] = f"""{{
  "timestamp": "2026-07-25T11:47:29Z",
  "level": "INFO",
  "service": "karti-odeme-motoru",
  "event": "payment.approved",
  "transactionId": "TRX-20260725-88340",
  "mti": "0110",
  "responseCode": "00",
  "responseReason": "Approved",
  "stan": "441511",
  "rrn": "{_rrn(101)}",
  "merchant": {{ "id": "MID-2002", "name": "Ege Market" }},
  "amount": 15975,
  "currency": "TRY",
  "threeDsResult": "authenticated",
  "customer": {{ "email": "{_PII['email_a']}" }},
  "message": "Approved after 3DS challenge - see api_3ds_initiate.md"
}}
"""

    logs["log_fast_success.json"] = f"""{{
  "timestamp": "2026-07-25T08:03:11Z",
  "level": "INFO",
  "service": "havale-fast-bridge",
  "event": "fast.transfer.completed",
  "transactionId": "TRX-20260725-51002",
  "senderBank": "Vera Bank",
  "amount": 5000,
  "currency": "TRY",
  "durationMs": 840,
  "customer": {{ "tckn": "{_PII['tckn_a']}" }},
  "message": "FAST transfer completed within expected latency"
}}
"""

    logs["log_fast_failed.json"] = f"""{{
  "timestamp": "2026-07-25T08:14:52Z",
  "level": "ERROR",
  "service": "havale-fast-bridge",
  "event": "fast.transfer.failed",
  "transactionId": "TRX-20260725-51009",
  "senderBank": "Vera Bank",
  "errorCode": "receiver_bank_timeout",
  "amount": 12000,
  "currency": "TRY",
  "customer": {{ "tckn": "{_PII['tckn_b']}", "phone": "{_PII['phone_a']}" }},
  "message": "Receiver bank did not acknowledge in time - see runbook_fast_failure.md"
}}
"""

    logs["log_openbanking_payment.json"] = f"""{{
  "timestamp": "2026-07-25T13:20:07Z",
  "level": "ERROR",
  "service": "openbanking-gateway",
  "event": "payment_order.failed",
  "transactionId": "TRX-20260725-63118",
  "errorCode": "consent_expired",
  "amount": 3200,
  "currency": "TRY",
  "customer": {{ "email": "{_PII['email_b']}", "tckn": "{_PII['tckn_a']}" }},
  "message": "Customer consent expired before payment order execution - see "
             "errorcodes_openbanking.md"
}}
"""

    logs["log_soap_webhook.xml"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <WebhookNotification>
      <EventType>payment.captured</EventType>
      <TransactionId>TRX-20260725-70044</TransactionId>
      <Merchant>Anadolu Tekstil</Merchant>
      <Signature>sha256=deadbeefcafef00d1234567890abcdef</Signature>
      <CustomerEmail>{_PII['email_a']}</CustomerEmail>
    </WebhookNotification>
  </soap:Body>
</soap:Envelope>
"""

    logs["log_soap_legacy_pos.xml"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <LegacyPosTransaction>
      <TerminalId>TRM3099</TerminalId>
      <ResponseCode>96</ResponseCode>
      <Message>System Malfunction - legacy SOAP bridge to {POS_SYSTEM}</Message>
    </LegacyPosTransaction>
  </soap:Body>
</soap:Envelope>
"""

    logs["log_openbanking_payment.xml"] = """<?xml version="1.0" encoding="UTF-8"?>
<paymentOrder>
  <consentId>CNS-99213</consentId>
  <status>rejected</status>
  <errorCode>account_not_found</errorCode>
  <amount currency="TRY">7500</amount>
  <message>Specified receiver account not found - see errorcodes_openbanking.md</message>
</paymentOrder>
"""

    return logs


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _generated_docs() -> dict[str, str]:
    docs: dict[str, str] = {}

    # RC-code family: runbook + json log + (6 of 9) xml log, with PII on a subset.
    pii_json_indices = {0, 4, 5, 6, 7}  # RC-05, RC-51, RC-54, RC-62, RC-91
    xml_codes = {"05", "51", "54", "62", "91", "96"}
    pii_xml_indices = {4, 5}  # RC-51, RC-54
    for i, rc in enumerate(_RC_CODES):
        name, body = _runbook_for_rc(rc)
        docs[name] = body
        name, body = _json_log_for_rc(rc, i, with_pii=i in pii_json_indices)
        docs[name] = body
        if rc["code"] in xml_codes:
            name, body = _xml_log_for_rc(rc, i, with_pii=i in pii_xml_indices)
            docs[name] = body

    # Extra RC-flavored runbooks not tied to a decline code.
    docs["runbook_arqc_failure.md"] = f"""# Runbook: ARQC Failure

Category: EMV / technical · Retry: No (do not blindly retry a cryptogram failure)

## Symptom
{AUTH_ENGINE} rejects a chip transaction because the Authorization Request Cryptogram
(ARQC) submitted by the card does not validate against the issuer's expected value.

## Likely cause
A corrupted or malfunctioning chip, a cloned/counterfeit card, or (rarely) an applet
bug on a specific card batch. See `errorcodes_emv.md`.

## Triage steps
1. Confirm this is isolated to one card, not a batch of cards from the same issuer.
2. Check whether the terminal firmware version matches the certified EMV kernel
   version — a mismatch can corrupt cryptogram generation.
3. If concentrated on one card, do not retry; this can indicate fraud.

## Resolution
Ask the cardholder to try a different card or a contactless/magstripe fallback where
permitted. Escalate a cluster of ARQC failures to the risk team immediately.
"""

    docs["runbook_cryptogram_mismatch.md"] = f"""# Runbook: Cryptogram Mismatch

Category: EMV / technical · Retry: Maybe

## Symptom
The issuer's host-side cryptogram verification fails during online authorization,
distinct from a terminal-side ARQC failure.

## Likely cause
Clock skew between the terminal and the issuer host, or a key-management
synchronization issue on the issuer side. See `errorcodes_emv.md`.

## Triage steps
1. Confirm the terminal's clock is synchronized (NTP) — skew is the most common cause.
2. Check whether the issue is isolated to one issuer's BIN range.
3. If terminal clock is correct, escalate to the issuer via {AUTH_ENGINE} support.

## Resolution
A single retry is safe if the terminal clock was the cause and has been corrected.
Persistent mismatches for one issuer require escalation, not repeated retries.
"""

    docs["runbook_3ds_failure.md"] = f"""# Prosedür: 3DS Kimlik Doğrulama Hatası

Kategori: kimlik doğrulama · Yeniden deneme: Belki

## Belirti
Kart hazır olmayan işlemler 3DS zorlu doğrulama (challenge) tamamlanamadığı için
başarısız oluyor.

## Olası Neden
ACS (Access Control Server) yanıt vermiyor, kart sahibi zorlu doğrulama penceresini
kapattı, ya da kart hatalı kayıtlı (enrollment sorunu). Bkz. `errorcodes_3ds.md`.

## İnceleme Adımları
1. Hatanın `errorcodes_3ds.md` içindeki hangi kategoriye girdiğini belirleyin.
2. ACS zaman aşımı şüphesi varsa 3DS sağlayıcı durum sayfasını kontrol edin.
3. Merchant genelinde bir artış varsa `postmortem_3ds_provider_outage.md` dosyasındaki
   emsal olaya bakın.

## Çözüm
Geçici ACS zaman aşımı: zorlu doğrulamayı bir kez daha deneyin. Tekrarlayan hatalarda
kart sahibini bankasıyla iletişime geçirin.
"""

    docs["runbook_fast_failure.md"] = f"""# Prosedür: FAST Transfer Başarısızlığı

Kategori: teknik · Yeniden deneme: Evet (idempotency anahtarıyla)

## Belirti
{FAST_BRIDGE} üzerinden gönderilen transferler tamamlanamıyor veya beklenenden çok
daha uzun sürüyor.

## Olası Neden
Alıcı bankanın sistemi geçici olarak yanıt vermiyor, günlük limit aşılmış, ya da
{FAST_BRIDGE}'in kendisinde bir kuyruk birikmesi var. Bkz. `errorcodes_fast.md`.

## İnceleme Adımları
1. Hata kodunun `receiver_bank_timeout` mi yoksa `bridge_unavailable` mı olduğunu
   belirleyin.
2. Alıcı banka bazında bir yoğunlaşma olup olmadığını kontrol edin.
3. Sürekli gecikme varsa `postmortem_fast_delay.md` dosyasındaki emsal olaya bakın.

## Çözüm
`receiver_bank_timeout` teknik bir hatadır, aynı işlem referansıyla güvenle tekrar
denenebilir. `account_not_found` ve `daily_limit_exceeded` için tekrar deneme
önerilmez.
"""

    docs["runbook_settlement_delay.md"] = f"""# Prosedür: Takas ve Mutabakat Gecikmeleri

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
"""

    # Family assembly: API, error catalogs, FAQ, concepts, guides, postmortems, traces.
    for slug, endpoint, purpose, detail in _API_ENDPOINTS:
        docs[f"api_{slug}.md"] = (
            f"# {slug.replace('_', ' ').title()} API Reference\n\n"
            f"`{endpoint}` — {purpose}.\n\n"
            f"## Usage\n{detail}\n\n"
            "## Idempotency\nSend a unique `stan` (System Trace Audit Number) on every "
            "write request so a retry never duplicates the operation — see "
            "`concept_iso8583_overview.md`.\n\n"
            "## Errors\nValidation failures return an internal RC in the 4xx-equivalent "
            "range with a `response_code`; upstream/technical failures return RC-91 or "
            "RC-96 and are safe to retry. See `errorcodes_iso8583.md` for the full table.\n"
        )

    docs.update(_errorcode_catalogs())

    for slug, title, lang, qas in _FAQ_TOPICS:
        header = f"# {'SSS' if lang == 'tr' else 'FAQ'}: {title}\n"
        lines = [header]
        q_label = "S" if lang == "tr" else "Q"
        a_label = "C" if lang == "tr" else "A"
        for question, answer in qas:
            lines.append(f"**{q_label}: {question}**\n{a_label}: {answer}\n")
        docs[f"faq_{slug}.md"] = "\n".join(lines)

    for slug, title, lang, text in _CONCEPTS:
        header = f"# {'Kavram' if lang == 'tr' else 'Concept'}: {title}\n\n"
        docs[f"concept_{slug}.md"] = header + text + "\n"

    for slug, title, lang, text in _GUIDES:
        header = f"# {'Yapılandırma Rehberi' if lang == 'tr' else 'Configuration Guide'}: {title}\n\n"
        docs[f"guide_{slug}.md"] = header + text + "\n"

    for slug, title, text in _POSTMORTEMS:
        docs[f"postmortem_{slug}.md"] = f"# Olay Sonrası Analiz (Postmortem): {title}\n\n{text}\n"

    for slug, exc, message, frame, with_pii in _TRACES:
        docs[f"trace_{slug}.txt"] = _trace_body(exc, message, frame, slug, with_pii=with_pii)

    docs.update(_extra_logs())

    return docs


def generate_corpus(corpus_dir: str) -> int:
    """Fully rebuild the synthetic corpus at ``corpus_dir``. Returns the number of files.

    This is a **full rebuild, not an append**: every existing file under ``corpus_dir``
    is removed before the new set is written, so a naming-scheme change (as happened in
    this v1 -> v2 rewrite) can never leave orphaned old documents behind. Safe because
    ``data/corpus/`` holds only generated content — nothing hand-maintained lives there.
    """

    root = Path(corpus_dir)
    root.mkdir(parents=True, exist_ok=True)

    removed = 0
    for existing in root.iterdir():
        if existing.is_file():
            existing.unlink()
            removed += 1
    if removed:
        logger.info("Cleared %d existing files from %s before rebuild.", removed, corpus_dir)

    all_docs = _generated_docs()
    for filename, content in all_docs.items():
        (root / filename).write_text(content, encoding="utf-8")

    logger.info("Generated %d synthetic documents in %s", len(all_docs), corpus_dir)
    return len(all_docs)
