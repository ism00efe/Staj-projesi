# Concept: PCI DSS Scope

Any system that stores, processes, or transmits raw card data falls within PCI DSS scope. Tokenization (see `concept_tokenization.md`) shrinks scope by keeping the PAN out of merchant and, where possible, internal systems. Logs must never contain a full PAN — masking is mandatory before storage, which is exactly what this system's sanitization layer enforces before anything reaches the knowledge base or an LLM prompt.
