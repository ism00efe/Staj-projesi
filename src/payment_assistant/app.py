"""Gradio user interface.

Strictly presentation: it builds the :class:`AssistantService` once and calls it. No
retrieval, prompting, or sanitization logic lives here (that all sits behind the
service). Labels are Turkish; the knowledge base and citations are English.
"""

from __future__ import annotations

import logging

import gradio as gr

from .config import configure_logging, get_settings
from .models import Answer
from .service import AssistantService, build_service

logger = logging.getLogger(__name__)


def _format_answer(answer: Answer) -> tuple[str, str, str]:
    """Turn an :class:`Answer` into (answer_md, sources_md, info_md) for the UI."""

    answer_md = answer.text or "_(Boş yanıt)_"

    if answer.citations:
        lines = ["### Kullanılan Kaynaklar (atıf yapılan)"]
        for c in answer.citations:
            lines.append(
                f"- **[{c.tag}]** {c.title} "
                f"`({c.doc_type}, {c.source_path}, benzerlik={c.score:.2f})`"
            )
        sources_md = "\n".join(lines)
    elif answer.retrieved:
        lines = ["### Getirilen Kaynaklar (atıf yapılmadı)"]
        for i, item in enumerate(answer.retrieved, start=1):
            c = item.chunk
            lines.append(
                f"- **[S{i}]** {c.title} "
                f"`({c.doc_type}, {c.source_path}, benzerlik={item.score:.2f})`"
            )
        sources_md = "\n".join(lines)
    else:
        sources_md = "_Kaynak bulunamadı._"

    if answer.redactions:
        info_md = "🔒 Maskelenen hassas veriler: " + ", ".join(answer.redactions)
    else:
        info_md = "🔒 Girdide maskelenecek hassas veri bulunmadı."

    return answer_md, sources_md, info_md


def build_ui(service: AssistantService) -> gr.Blocks:
    """Construct the Gradio Blocks app around an existing service."""

    def on_submit(question: str, file_obj) -> tuple[str, str, str]:
        # Gradio's File returns a str path (type="filepath") or an object with .name
        # depending on version; handle both.
        if file_obj is None:
            file_path = None
        elif isinstance(file_obj, str):
            file_path = file_obj
        else:
            file_path = file_obj.name
        if not (question and question.strip()) and not file_path:
            return (
                "Lütfen bir soru yazın veya bir log dosyası yükleyin.",
                "",
                "",
            )
        try:
            answer = service.ask_with_log_file(question, file_path)
        except Exception as exc:  # surface errors to the user instead of crashing the UI
            logger.exception("Query failed")
            return (f"⚠️ Bir hata oluştu: {exc}", "", "")
        return _format_answer(answer)

    with gr.Blocks(title="Ödeme Sistemleri Asistanı") as demo:
        gr.Markdown(
            "# 💳 Ödeme Sistemleri Bilgi & Log Analiz Asistanı\n"
            "Bir sorun giderme sorusu sorun veya bir JSON/XML log dosyası yükleyin. "
            "Sistem, bilgi tabanından ilgili kaynakları getirir ve **kaynak atıflı** "
            "bir yanıt üretir. Girdilerdeki hassas veriler (kart, TCKN, e-posta, IP, "
            "telefon, token) **gönderilmeden önce maskelenir**."
        )
        with gr.Row():
            with gr.Column(scale=3):
                question = gr.Textbox(
                    label="Sorunuz",
                    placeholder="Örn: 3D Secure doğrulaması neden timeout veriyor?",
                    lines=3,
                )
                log_file = gr.File(
                    label="Log dosyası (opsiyonel, JSON/XML/TXT)",
                    file_types=[".json", ".xml", ".txt", ".log"],
                )
                submit = gr.Button("Sorgula", variant="primary")
            with gr.Column(scale=4):
                answer_out = gr.Markdown(label="Yanıt")
                info_out = gr.Markdown()
                sources_out = gr.Markdown()

        submit.click(
            on_submit,
            inputs=[question, log_file],
            outputs=[answer_out, sources_out, info_out],
        )
        gr.Examples(
            examples=[
                ["Bir ödeme 'insufficient funds' hatası verdi, ne yapmalıyım?"],
                ["Idempotency key ne işe yarar ve nasıl kullanılır?"],
                ["Webhook imza doğrulaması nasıl yapılır?"],
            ],
            inputs=[question],
        )

    return demo


def main() -> None:
    configure_logging()
    settings = get_settings()
    service = build_service(settings)
    logger.info("Knowledge base contains %d chunks.", service.knowledge_base_size())
    demo = build_ui(service)
    demo.launch(server_name=settings.app_host, server_port=settings.app_port)


if __name__ == "__main__":
    main()
