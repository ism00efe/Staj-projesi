# Concept: ISO 20022 / SWIFT Messaging

ISO 20022 is the XML-based messaging standard increasingly replacing older SWIFT MT formats for cross-border and interbank payments. Key message types: `pacs.008` (FI-to-FI customer credit transfer), `pacs.002` (payment status report), `camt.053` (bank-to-customer statement), `camt.056` (payment cancellation request). Unlike ISO 8583's compact binary-ish fields, ISO 20022 messages are structured, self-describing XML, better suited to cross-border compliance data.
