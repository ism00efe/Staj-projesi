"""Generate the synthetic knowledge-base corpus.

Usage:  python scripts/generate_data.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (adds src/ to sys.path)

from payment_assistant.config import configure_logging, get_settings
from payment_assistant.datagen import generate_corpus


def main() -> None:
    configure_logging()
    settings = get_settings()
    count = generate_corpus(settings.corpus_dir)
    print(f"Generated {count} documents in {settings.corpus_dir}")
    print("Next: python scripts/ingest.py")


if __name__ == "__main__":
    main()
