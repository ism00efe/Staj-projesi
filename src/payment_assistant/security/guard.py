"""Prompt injection guard.

A deterministic, regex-based pre-filter that inspects the retrieval query — already
sanitized of PII by this point (see ``rag.engine.RAGEngine.answer``) — before it reaches
retrieval or the LLM. Mirrors ``sanitization.py``'s philosophy: rule-based, no LLM,
narrow and auditable. This is a coarse first line of defense against the well-known
override/jailbreak patterns, not general content moderation.

Known limitation: patterns target the common English jailbreak phrasing ("ignore
previous instructions", etc.). A determined attacker phrasing an injection in Turkish
could evade them, the same inherent limit deterministic regex sanitization already has.
See DECISIONS.md.
"""

from __future__ import annotations

import re

REFUSAL_MESSAGE = (
    "Bu istek güvenlik nedeniyle işlenemedi. Lütfen sorunuzu farklı bir şekilde "
    "ifade edin."
)

# Attempts to override/replace the system prompt's instructions.
_INSTRUCTION_OVERRIDE = re.compile(
    r"(?i)\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?"
    r"(previous|prior|above|earlier|preceding)\s+(instructions?|prompts?|rules?)\b"
)

# Attempts to reassign the assistant's persona ("you are now...", classic jailbreaks).
_PERSONA_OVERRIDE = re.compile(
    r"(?i)\byou\s+are\s+now\b|\back\s+as\b.{0,20}\bDAN\b|\bjailbreak\b|\bDAN\s+mode\b"
)

# A line that tries to inject a new "system:" / "assistant:" / "user:" turn into the
# conversation, smuggling fake roles into what should be plain user content.
_ROLE_SWITCH = re.compile(r"(?im)^\s*(system|assistant|user)\s*:")

# Chat-template control tokens that have no business appearing in a user question.
_SPECIAL_TOKENS = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|\[/?INST\]|<<SYS>>|<</SYS>>|<\|endoftext\|>"
)

# Attempts to exfiltrate the system prompt itself.
_PROMPT_LEAK = re.compile(
    r"(?i)\b(reveal|print|show|display|repeat)\b.{0,30}\bsystem\s+prompt\b"
)

# Checked in order; first match wins. Order doesn't affect the outcome (any match
# blocks), only which `reason` is reported.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_INSTRUCTION_OVERRIDE, "instruction_override"),
    (_PERSONA_OVERRIDE, "persona_override"),
    (_ROLE_SWITCH, "role_switch"),
    (_SPECIAL_TOKENS, "special_token"),
    (_PROMPT_LEAK, "prompt_leak"),
)


def inspect_query(query: str) -> tuple[bool, str]:
    """Inspect ``query`` for prompt-injection patterns.

    Returns ``(safe, reason)``. ``safe=True`` means nothing suspicious was found and
    ``reason`` is ``"ok"``. ``safe=False`` means the query should be refused; ``reason``
    is a fixed, low-cardinality category name (never the raw match) safe to log or use
    as a metric label.
    """

    if not query:
        return True, "ok"
    for pattern, reason in _PATTERNS:
        if pattern.search(query):
            return False, reason
    return True, "ok"
