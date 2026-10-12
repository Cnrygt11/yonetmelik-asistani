"""Gradio arayüzü (Faz 5, K-15: Colab'da çalışan sistem).

    python -m yonetmelik_asistani.ui [--share]

Colab'da --share herkese açık geçici bir bağlantı üretir; bağlantı oturum kapanınca kapanır (plan 12.1).
Geri bildirim ve kayıt (plan Faz 5) aydınlatma metniyle birlikte eklenecek; şimdilik hiçbir şey saklanmaz.
"""

from __future__ import annotations

import argparse

from yonetmelik_asistani.ui.service import (
    BIRIMLER,
    DUZEYLER,
    UYARI,
    AssistantService,
    render_sources,
)


def build_service() -> AssistantService:
    from yonetmelik_asistani.config import REPO_ROOT, load_config
    from yonetmelik_asistani.generation.llm_client import LLMClient
    from yonetmelik_asistani.generation.pipeline import load_maddeler, load_repealed
    from yonetmelik_asistani.retrieval.service import load_retriever

    cfg = load_config()
    return AssistantService(
        retriever=load_retriever(cfg),
        llm=LLMClient(cfg.llm),
        maddeler=load_maddeler(cfg.data_dir / "processed"),
        repealed=load_repealed(REPO_ROOT / cfg.section("paths").get("manifest", "configs/corpus_manifest.yaml")),
        budget=cfg.section("retrieval").get("context_token_budget", 5000),
        rel_rerank=cfg.section("generation").get("rel_rerank", 0.1),
    )


def build_ui(service: AssistantService, corpus_version: str = ""):
    import gradio as gr

    birim_map = dict(BIRIMLER)
    duzey_map = dict(DUZEYLER)

    def on_ask(soru, birim_adi, duzey_adi):
        r = service.ask(soru, birim=birim_map.get(birim_adi), duzey=duzey_map.get(duzey_adi))
        notlar = "".join(f"\n\n<sub>{n}</sub>" for n in r.terim_notlari)
        sure = f"\n\n<sub>{r.sure_s} sn</sub>" if r.sure_s else ""
        return r.cevap + notlar + sure, render_sources(r.kaynaklar) or "_Gösterilecek kaynak yok._"

    with gr.Blocks(title="Yönetmelik Asistanı") as demo:
        gr.Markdown(f"## Yönetmelik Asistanı\nBursa Uludağ Üniversitesi önlisans ve lisans öğrenci mevzuatı · "
                    f"belge sürümü {corpus_version}\n\n<sub>{UYARI}</sub>")
        with gr.Row():
            birim = gr.Dropdown([b for b, _ in BIRIMLER], value=BIRIMLER[0][0], label="Fakülte / birim")
            duzey = gr.Dropdown([d for d, _ in DUZEYLER], value=DUZEYLER[0][0], label="Düzey")
        soru = gr.Textbox(label="Sorunuz", placeholder="ör. kaydımı dondurmak istiyorum, ne zamana kadar başvurmalıyım?",
                          lines=2)
        sor = gr.Button("Sor", variant="primary")
        cevap = gr.Markdown()
        with gr.Accordion("Kaynaklar", open=False):
            kaynaklar = gr.Markdown()
        sor.click(on_ask, [soru, birim, duzey], [cevap, kaynaklar])
        soru.submit(on_ask, [soru, birim, duzey], [cevap, kaynaklar])
        gr.Examples(["tek ders sınavına kimler girebiliyor", "harcımı ödemezsem okuldan atılır mıyım",
                     "yaz okulunda en fazla kaç ders alabilirim", "devamsızlıktan kalan büte girebilir mi"], soru)
    return demo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.ui")
    ap.add_argument("--share", action="store_true", help="geçici herkese açık bağlantı (Colab)")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args(argv)
    from yonetmelik_asistani.config import load_config

    demo = build_ui(build_service(), load_config().corpus_version)
    demo.launch(share=args.share, server_port=args.port)
    return 0
