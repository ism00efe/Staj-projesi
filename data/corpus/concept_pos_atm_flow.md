# Concept: POS / ATM Transaction Lifecycle

A card-present transaction moves through four stages: **authorization** (an ISO 8583 MTI 0100 request holds funds), **capture** (the merchant settles the authorized amount, converting it to a receivable), **settlement** (captured transactions clear in a batch, moving funds from acquirer to merchant), and **chargeback** (the cardholder's issuer can still force a reversal after settlement, within the scheme's dispute window). See `api_authorization.md`, `api_capture.md`, and `faq_ters_ibraz.md`.
