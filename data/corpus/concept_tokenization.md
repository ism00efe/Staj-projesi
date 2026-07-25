# Concept: Tokenization

Tokenization replaces a card number (PAN) with a surrogate value usable only by the merchant it was issued to. The raw PAN never touches merchant systems after the initial exchange, which is what keeps most merchants out of full PCI DSS scope for storage. Tokens survive card expiry through account-updater services and underpin saved-card and recurring-billing flows. See `api_tokenization.md`.
