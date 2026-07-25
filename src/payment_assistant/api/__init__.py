"""HTTP layer: the JSON contract every client speaks.

Transport only — validation, limits, error rendering, and mapping domain objects onto
the wire format. All behavior lives behind ``AssistantService``.
"""

from .app import create_app, main

__all__ = ["create_app", "main"]
