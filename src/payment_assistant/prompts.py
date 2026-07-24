"""Prompt templates (versioned so evaluation can A/B compare them).

The knowledge base is English; the assistant answers in Turkish and cites sources by the
``[S1]..[Sk]`` tags injected into the context. Grounding rules are explicit to reduce
hallucination and to force citations.
"""

from __future__ import annotations

from .models import RetrievedChunk

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """Sen, ödeme sistemleri (payment systems) konusunda uzman bir teknik \
destek asistanısın. Görevin, sağlanan kaynak belgelere dayanarak mühendislere sorun \
giderme (troubleshooting) rehberliği sunmaktır.

Kurallar:
- SADECE aşağıda verilen KAYNAKLAR bölümündeki bilgilere dayan. Kaynaklarda olmayan \
bilgi uydurma.
- Cevabı Türkçe ver. Teknik terimleri (ör. timeout, retry, idempotency, HTTP kodları, \
hata kodları) İngilizce olarak koruyabilirsin.
- Kullandığın her bilgi için ilgili kaynağı [S1], [S2] gibi etiketlerle cümle sonunda \
belirt.
- Eğer kaynaklar soruyu yanıtlamak için yeterli değilse, bunu açıkça söyle ve tahmin \
yürütme.
- Mümkün olduğunda cevabı adım adım (numaralı liste) ve uygulanabilir şekilde ver.
- Kaynaklardaki [EMAIL], [CARD], [IP], [TCKN], [PHONE], [TOKEN] gibi maskeler hassas \
verinin gizlendiğini gösterir; bunları olduğu gibi bırak."""


def _format_sources(retrieved: list[RetrievedChunk]) -> str:
    blocks = []
    for i, item in enumerate(retrieved, start=1):
        c = item.chunk
        blocks.append(
            f"[S{i}] (type={c.doc_type}, title={c.title})\n{c.text.strip()}"
        )
    return "\n\n".join(blocks)


def build_user_prompt(question: str, retrieved: list[RetrievedChunk]) -> str:
    """Assemble the grounded user prompt from the question and retrieved context."""

    sources = _format_sources(retrieved) if retrieved else "(Kaynak bulunamadı.)"
    return (
        f"SORU:\n{question}\n\n"
        f"KAYNAKLAR:\n{sources}\n\n"
        "Yukarıdaki kaynaklara dayanarak soruyu yanıtla ve kullandığın kaynakları "
        "[S1], [S2] biçiminde belirt."
    )
