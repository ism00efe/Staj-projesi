"""Cross-cutting security concerns beyond PII sanitization (see ``sanitization.py``)."""

from .guard import REFUSAL_MESSAGE, inspect_query

__all__ = ["inspect_query", "REFUSAL_MESSAGE"]
