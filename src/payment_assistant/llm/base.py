"""LLM provider interface.

The RAG engine depends only on this protocol — never on a vendor SDK. Concrete providers
live next to this file and are chosen by ``LLM_PROVIDER`` via the factory in
``__init__.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Raised when a provider call fails (network, auth, bad response)."""


@runtime_checkable
class LLMProvider(Protocol):
    """Generates a completion from a system + user prompt."""

    def generate(self, system: str, user: str) -> str: ...

    @property
    def name(self) -> str: ...
