"""Wire format for the HTTP API.

These pydantic models are the *only* place the internal domain dataclasses
(:mod:`payment_assistant.models`) are translated into JSON. Keeping the mapping here
rather than in the route handler is what lets the controller stay thin — it calls the
service and hands the result to :meth:`AnalyzeResponse.from_answer`.

The response shape is a public contract: three separate clients (the web UI, the Visual
Studio extension, and anything using ``/docs``) depend on it.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from ..models import Answer
from ..security import REFUSAL_MESSAGE

logger = logging.getLogger(__name__)

# How much of a source chunk to show in the collapsible source list. Long enough to judge
# relevance at a glance, short enough that a top_k response stays small. A presentation
# constant, not a knob worth an env var.
_EXCERPT_CHARS = 300

# `rag/engine.py` flattens structured Redaction(label, count) objects into display
# strings ("[CARD]×1") before they reach Answer. That module is not ours to change, so we
# parse them back apart here. The separator is U+00D7 MULTIPLICATION SIGN, not "x".
_REDACTION_SEP = "×"


class AnalyzeRequest(BaseModel):
    """One analysis request.

    ``extra="forbid"`` is a security control, not tidiness: a client that sends
    ``{"file_path": "/etc/passwd"}`` gets a 422 instead of having the field silently
    ignored. It makes "this API never accepts file paths" an enforced contract rather
    than a convention.
    """

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(
        default=None,
        description="Kullanıcının sorusu.",
        examples=["3D Secure doğrulaması neden timeout veriyor?"],
    )
    file_content: str | None = Field(
        default=None,
        description=(
            "Opsiyonel log dosyasının metin içeriği. Dosya yolu kabul edilmez — "
            "istemci dosyayı kendisi okuyup içeriğini gönderir."
        ),
    )


class SourceItem(BaseModel):
    """One knowledge-base source behind an answer."""

    tag: str = Field(description='Atıf etiketi, ör. "S1".')
    title: str
    doc_type: str = Field(description='Belge türü, ör. "runbook", "faq", "error_codes".')
    source_path: str
    score: float = Field(description="Benzerlik skoru (yüksek = daha ilgili).")
    document_id: str
    cited: bool = Field(
        description=(
            "True ise yanıt bu kaynağa açıkça atıf yaptı; False ise kaynak getirildi "
            "ama yanıtta atıf yapılmadı."
        )
    )
    excerpt: str | None = Field(default=None, description="Kaynak metninden kısa bir alıntı.")


class RedactionItem(BaseModel):
    """How many values of one sensitive-data category were masked."""

    label: str = Field(description='Maskeleme etiketi, ör. "[CARD]".')
    count: int


class SecuritySummary(BaseModel):
    """What the security layer did to this request."""

    blocked: bool = Field(description="İstek güvenlik filtresi tarafından reddedildi mi?")
    redactions: list[RedactionItem]
    redaction_total: int


class AnalyzeResponse(BaseModel):
    """The analysis result returned to every client."""

    answer: str
    sources: list[SourceItem]
    security_summary: SecuritySummary
    trace_id: str = Field(description="Bu isteğin izleme kimliği; log kayıtlarıyla eşleşir.")

    @classmethod
    def from_answer(cls, answer: Answer, *, fallback_trace_id: str) -> AnalyzeResponse:
        """Map a domain :class:`Answer` onto the wire format."""

        return cls(
            answer=answer.text,
            sources=_build_sources(answer),
            security_summary=_build_security_summary(answer),
            trace_id=answer.trace_id or fallback_trace_id,
        )


class ErrorBody(BaseModel):
    """Machine-readable code + a user-facing Turkish message."""

    code: str
    message: str
    fields: list[str] | None = Field(
        default=None,
        description=(
            "Doğrulama hatalarında sorunlu alan adları. Gönderilen *değerler* asla "
            "burada yer almaz."
        ),
    )


class ErrorResponse(BaseModel):
    """Error envelope.

    Deliberately a different shape from :class:`AnalyzeResponse` so a client can never
    mistake a failure for an empty success.
    """

    error: ErrorBody
    trace_id: str


class HealthResponse(BaseModel):
    """Liveness plus the two facts a client needs before it can submit anything."""

    status: str
    knowledge_base_size: int
    max_upload_bytes: int


def _build_sources(answer: Answer) -> list[SourceItem]:
    """Cited sources if the model used any, otherwise what was retrieved.

    This preserves the distinction the previous UI drew ("atıf yapılan" vs. "atıf
    yapılmadı"): an answer with no ``[S#]`` tags still shows what the assistant read, so
    a user can judge whether the retrieval was reasonable.
    """

    if answer.citations:
        return [
            SourceItem(
                tag=c.tag,
                title=c.title,
                doc_type=c.doc_type,
                source_path=c.source_path,
                score=c.score,
                document_id=c.document_id,
                cited=True,
                excerpt=_excerpt_for_tag(answer, c.tag),
            )
            for c in answer.citations
        ]

    return [
        SourceItem(
            tag=f"S{i}",
            title=item.chunk.title,
            doc_type=item.chunk.doc_type,
            source_path=item.chunk.source_path,
            score=item.score,
            document_id=item.chunk.document_id,
            cited=False,
            excerpt=_truncate(item.chunk.text),
        )
        for i, item in enumerate(answer.retrieved, start=1)
    ]


def _excerpt_for_tag(answer: Answer, tag: str) -> str | None:
    """Recover a citation's source text via its tag.

    ``Citation`` carries no text, but ``rag/engine.py`` builds every tag as
    ``f"S{idx}"`` where ``idx`` is a 1-based index into ``answer.retrieved`` — so the
    tag is the join key back to the chunk.
    """

    try:
        index = int(tag[1:]) - 1
    except ValueError:
        return None
    if 0 <= index < len(answer.retrieved):
        return _truncate(answer.retrieved[index].chunk.text)
    return None


def _truncate(text: str) -> str:
    if len(text) <= _EXCERPT_CHARS:
        return text
    return text[:_EXCERPT_CHARS].rstrip() + "…"


def _build_security_summary(answer: Answer) -> SecuritySummary:
    redactions = [_parse_redaction(label) for label in answer.redactions]
    return SecuritySummary(
        # The engine signals a guard block only through the answer text. We compare
        # against the exported constant rather than a copied literal, so the two cannot
        # drift apart silently. See DECISIONS.md D22 for why no cleaner channel exists.
        blocked=answer.text == REFUSAL_MESSAGE,
        redactions=redactions,
        redaction_total=sum(r.count for r in redactions),
    )


def _parse_redaction(label: str) -> RedactionItem:
    """Split ``"[CARD]×2"`` back into its label and count.

    On an unrecognized format we log and degrade to a count of 1 rather than failing the
    whole request — this is a display field, and losing a working answer over it would be
    the wrong trade. The loud failure lives in a contract test that runs the real engine
    and asserts every label it produces parses here, so format drift breaks CI instead of
    a user's request. The raw value is never logged: if it didn't parse, we cannot prove
    it isn't user content.
    """

    name, separator, raw_count = label.rpartition(_REDACTION_SEP)
    if separator and raw_count.isdigit():
        return RedactionItem(label=name, count=int(raw_count))

    logger.warning(
        "unparsable redaction label",
        extra={"status": "error", "reason": "redaction_label_format"},
    )
    return RedactionItem(label=label, count=1)
