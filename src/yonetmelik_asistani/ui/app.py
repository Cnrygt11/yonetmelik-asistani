"""Gradio arayüzü (Faz 5, K-15: Colab'da çalışan sistem).

    python -m yonetmelik_asistani.ui [--share] [--kayit reports/arayuz_kayit.jsonl]

Colab'da --share herkese açık geçici bir bağlantı üretir; bağlantı oturum kapanınca kapanır (plan 12.1).
--kayit verilirse her soru, cevap ve kullanıcının değerlendirmesi (doğru / kısmen / yanlış / emin değilim)
JSONL dosyasına eklenir ve arayüzün başında bunu söyleyen bir uyarı görünür. Canlı test oturumları
gerçek soru verisi üretir (FAZ_4.md: ana ölçüt gerçek öğrenci soruları). Kayıt yoksa hiçbir şey saklanmaz.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

from yonetmelik_asistani.ui.service import (
    BIRIMLER,
    DUZEYLER,
    UYARI,
    AssistantService,
    render_sources,
)

# Canlı testte tek seçim; tanımlar kör puanlama uzlaşmasıyla aynı (FAZ_4.md): yeterli = yanıltıcı bilgi yok,
# asıl soru cevaplanmış, önemli koşul atlanmamış. Tek bir yanlış cümle bile cevabı yanıltıcı yapar.
KARARLAR = {"Yeterli": "yeterli", "Yanıltıcı bilgi var": "yaniltici", "Eksik ya da soruyu cevaplamadı": "eksik",
            "Emin değilim": "emin_degilim"}
GECMIS_TUR = 2  # takip sorusu için hatırlanan önceki soru sayısı


class Kayit:
    """Arayüz kaydı: satır başına bir olay (soru, değerlendirme, hata). Yol yoksa hiçbir şey yazılmaz."""

    def __init__(self, path: Path | None = None, corpus_version: str = "") -> None:
        self.path = Path(path) if path else None
        self.corpus_version = corpus_version

    def yaz(self, row: dict) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"tarih": datetime.now().isoformat(timespec="seconds"), **row},
                               ensure_ascii=False) + "\n")


def ask_handler(service: AssistantService, kayit: Kayit, soru: str, birim_adi: str, duzey_adi: str,
                onceki_id: str | None, gecmis: list[tuple[str, str]] | None = None
                ) -> tuple[str, str, str | None, str | None]:
    """→ (cevap, kaynaklar, kayıt kimliği, düz cevap). onceki_id aynı tarayıcıdaki bir önceki soru; gecmis
    takip sorusu için son (soru, cevap) çiftleri. Düz cevap yalnızca başarılı soruda döner (geçmişe eklenir)."""
    qid = uuid.uuid4().hex[:8]
    try:
        r = service.ask(soru, birim=dict(BIRIMLER).get(birim_adi), duzey=dict(DUZEYLER).get(duzey_adi),
                        gecmis=gecmis)
    except (RuntimeError, ValueError, OSError) as e:  # LLMError (Ollama düştü), CUDA belleği; arayüz açık kalır
        kayit.yaz({"tur": "hata", "id": qid, "onceki_id": onceki_id, "soru": soru, "hata": f"{type(e).__name__}: {e}"})
        return f"Bir hata oluştu ({type(e).__name__}). Birkaç saniye sonra tekrar deneyin.", "", onceki_id, None
    if not r.kayit:  # boş soru
        return r.cevap, "", onceki_id, None
    kayit.yaz({"tur": "soru", "id": qid, "onceki_id": onceki_id, "corpus_version": kayit.corpus_version,
               **r.kayit})
    anlasilan = (f"\n\n<sub>Soruyu şöyle anladım: {r.kayit['yeniden_yazilan']}</sub>"
                 if r.kayit.get("yeniden_yazilan") else "")
    notlar = "".join(f"\n\n<sub>{n}</sub>" for n in r.terim_notlari)
    alt = [f"{r.sure_s} sn"] if r.sure_s else []
    if kayit.path:
        alt.append(f"kayıt {qid}")
    return (r.cevap + anlasilan + notlar + (f"\n\n<sub>{' · '.join(alt)}</sub>" if alt else ""),
            render_sources(r.kaynaklar) or "_Gösterilecek kaynak yok._", qid, r.cevap)


def feedback_handler(kayit: Kayit, qid: str | None, karar: str | None, not_: str | None) -> str:
    if not qid:
        return "Önce bir soru sorun."
    if karar not in KARARLAR:
        return "Bir seçenek işaretleyin."
    kayit.yaz({"tur": "degerlendirme", "id": qid, "karar": KARARLAR[karar], "not": (not_ or "").strip()})
    return f"Kaydedildi: {karar}. Fikrinizi değiştirirseniz yeniden kaydedebilirsiniz; son kayıt geçerlidir."


def build_service() -> tuple[AssistantService, bool]:
    """→ (hizmet, takip sorusu desteği açık mı)."""
    from yonetmelik_asistani.config import REPO_ROOT, load_config
    from yonetmelik_asistani.generation.llm_client import LLMClient
    from yonetmelik_asistani.generation.pipeline import load_links, load_maddeler, load_repealed
    from yonetmelik_asistani.retrieval.service import load_retriever

    cfg = load_config()
    gen = cfg.section("generation")
    return AssistantService(
        retriever=load_retriever(cfg),
        llm=LLMClient(cfg.llm),
        maddeler=load_maddeler(cfg.data_dir / "processed"),
        repealed=load_repealed(REPO_ROOT / cfg.section("paths").get("manifest", "configs/corpus_manifest.yaml")),
        budget=cfg.section("retrieval").get("context_token_budget", 5000),
        rel_rerank=gen.get("rel_rerank", 0.1),
        max_sources=gen.get("max_sources"),
        links=load_links(REPO_ROOT / gen["ilgili_maddeler"]) if gen.get("ilgili_maddeler") else {},
        dogrula=gen.get("dogrulama", False),
    ), gen.get("takip", True)


def build_ui(service: AssistantService, corpus_version: str = "", kayit: Kayit | None = None, takip: bool = True):
    import gradio as gr

    kayit = kayit or Kayit(None, corpus_version)
    kayit_notu = ("\n\n<sub>**Bu oturumda sorular, cevaplar ve değerlendirmeler geliştirme amacıyla "
                  "kaydediliyor.** Ad, öğrenci numarası gibi kişisel bilgi yazmayın.</sub>" if kayit.path else "")
    hafiza_notu = (f"Asistan son {GECMIS_TUR} sorunu hatırlar; başka bir konuya geçerken **Yeni konu**'ya basın."
                   if takip else "Asistan önceki soruları hatırlamaz; her soru ayrı cevaplanır.")

    def on_ask(soru, birim_adi, duzey_adi, onceki_id, gecmis):
        cevap_md, kaynak_md, qid, duz = ask_handler(service, kayit, soru, birim_adi, duzey_adi, onceki_id,
                                                    gecmis if takip else None)
        if duz is not None and takip:
            gecmis = ([*(gecmis or []), (soru, duz)])[-GECMIS_TUR:]
        return cevap_md, kaynak_md, qid, gecmis, None, "", ""  # yeni cevap: değerlendirme alanları sıfırlanır

    with gr.Blocks(title="Yönetmelik Asistanı") as demo:
        gr.Markdown(f"## Yönetmelik Asistanı\nBursa Uludağ Üniversitesi önlisans ve lisans öğrenci mevzuatı · "
                    f"belge sürümü {corpus_version}\n\n<sub>{UYARI}</sub>\n\n<sub>{hafiza_notu}</sub>{kayit_notu}")
        son_id = gr.State(None)
        gecmis = gr.State([])
        with gr.Row():
            birim = gr.Dropdown([b for b, _ in BIRIMLER], value=BIRIMLER[0][0], label="Fakülte / birim")
            duzey = gr.Dropdown([d for d, _ in DUZEYLER], value=DUZEYLER[0][0], label="Düzey")
        soru = gr.Textbox(label="Sorunuz", placeholder="ör. kaydımı dondurmak istiyorum, ne zamana kadar başvurmalıyım?",
                          lines=2)
        with gr.Row():
            sor = gr.Button("Sor", variant="primary")
            yeni = gr.Button("Yeni konu", visible=takip)
        cevap = gr.Markdown()
        with gr.Accordion("Kaynaklar", open=False):
            kaynaklar = gr.Markdown()
        with gr.Column(visible=kayit.path is not None):
            karar = gr.Radio(list(KARARLAR), label="Bu cevap nasıldı?")
            not_ = gr.Textbox(label="Not (isteğe bağlı)", lines=1,
                              placeholder="ör. doğrusu şu olmalıydı / hangi cümle yanlış / soruyu yanlış anladı")
            kaydet = gr.Button("Değerlendirmeyi kaydet")
            durum = gr.Markdown()
        outputs = [cevap, kaynaklar, son_id, gecmis, karar, not_, durum]
        sor.click(on_ask, [soru, birim, duzey, son_id, gecmis], outputs)
        soru.submit(on_ask, [soru, birim, duzey, son_id, gecmis], outputs)
        yeni.click(lambda: ([], "_Yeni konu: önceki sorular unutuldu._"), None, [gecmis, cevap])
        kaydet.click(lambda qid, k, n: feedback_handler(kayit, qid, k, n), [son_id, karar, not_], durum)
        gr.Examples(["tek ders sınavına kimler girebiliyor", "harcımı ödemezsem okuldan atılır mıyım",
                     "yaz okulunda en fazla kaç ders alabilirim", "devamsızlıktan kalan büte girebilir mi"], soru)
    return demo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.ui")
    ap.add_argument("--share", action="store_true", help="geçici herkese açık bağlantı (Colab)")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--kayit", type=Path, help="soru, cevap ve değerlendirmeleri bu JSONL dosyasına ekle")
    args = ap.parse_args(argv)
    from yonetmelik_asistani.config import load_config

    corpus_version = load_config().corpus_version
    if args.kayit:
        print(f"Kayıt açık: {args.kayit}")
    service, takip = build_service()
    demo = build_ui(service, corpus_version, Kayit(args.kayit, corpus_version), takip=takip)
    demo.launch(share=args.share, server_port=args.port)
    return 0
