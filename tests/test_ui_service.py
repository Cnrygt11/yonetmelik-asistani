import json
import types

from yonetmelik_asistani.generation.prompts import RET_CUMLESI
from yonetmelik_asistani.retrieval.hybrid import Hit
from yonetmelik_asistani.ui.service import AssistantService, render_sources

MADDELER = {"eoy:md19": {"path": "EÖY › Madde 19 (İzinli ayrılma)", "text": "(1) 10 iş günü içinde başvurulur.",
                         "meta": {"doc_type": "kurum_yonetmeligi", "birim": ["tum"],
                                  "kaynak_url": "https://kms.kaysis.gov.tr/Home/Goster/167318"}},
            "eoy:md10": {"path": "EÖY › Madde 10", "text": "Kayıt yenileme.", "meta": {"birim": ["tum"]}}}
CHUNKS = {"eoy:md19": {"text": "x\n10 iş günü"}, "eoy:md10": {"text": "x\nkayıt"}}


class Retriever:
    chunks = CHUNKS
    expander = None
    def __init__(self):
        self.profiles = []
        self.last_expansion = []

    def search(self, q, profile=None, mode="hybrid_rerank", k=None):
        self.profiles.append(profile)
        return [Hit("eoy:md19", "eoy:md19", 1.0, {"rerank": 0.9}), Hit("eoy:md10", "eoy:md10", 0.5, {"rerank": 0.5})]


class LLM:
    def __init__(self, text):
        self.text = text

    def chat(self, messages, **kwargs):
        return types.SimpleNamespace(text=self.text, wall_s=1.2, model="sahte", prompt_tokens=None)


def v3(cevap, alintilar=()):
    return json.dumps({"alintilar": [{"kaynak": k, "metin": m} for k, m in alintilar], "cevap": cevap,
                       "ayrintilar": [], "eksik": False}, ensure_ascii=False)


def test_service_returns_only_cited_sources_and_passes_profile():
    r = Retriever()
    s = AssistantService(r, LLM(v3("10 iş günü içinde başvurulur [K1].", [("K1", "10 iş günü içinde başvurulur.")])),
                         MADDELER)
    res = s.ask("kaydımı dondurmak istiyorum", birim="muhendislik-fakultesi", duzey="lisans")
    assert [k["etiket"] for k in res.kaynaklar] == ["K1"]
    assert r.profiles[-1] == {"birim": "muhendislik-fakultesi", "duzey": "lisans"}
    md = render_sources(res.kaynaklar)
    assert "İzinli ayrılma" in md and "kms.kaysis.gov.tr" in md


def test_service_refusal_has_no_sources_and_empty_question():
    s = AssistantService(Retriever(), LLM(v3(RET_CUMLESI)), MADDELER)
    res = s.ask("yurt ücreti ne kadar")
    assert res.ret and res.kaynaklar == []
    assert s.ask("   ").cevap == "Lütfen bir soru yazın."


def test_service_v2_plain_text_path_still_works():
    s = AssistantService(Retriever(), LLM("10 iş günü içinde başvurulur [K1]."), MADDELER, istem="v2")
    res = s.ask("kaydımı dondurmak istiyorum")
    assert not res.ret and [k["etiket"] for k in res.kaynaklar] == ["K1"]


def test_ask_and_feedback_are_logged_with_previous_question(tmp_path):
    from yonetmelik_asistani.ui.app import Kayit, ask_handler, feedback_handler

    s = AssistantService(Retriever(), LLM(v3("10 iş günü içinde başvurulur [K1].",
                                              [("K1", "10 iş günü içinde başvurulur.")])), MADDELER)
    k = Kayit(tmp_path / "k.jsonl", "2026.10.2")
    cevap, kaynak, q1 = ask_handler(s, k, "kaydımı dondurmak istiyorum", "Mühendislik Fakültesi", "Lisans", None)
    assert "[K1]" in cevap and f"kayıt {q1}" in cevap and "İzinli ayrılma" in kaynak
    _, _, q2 = ask_handler(s, k, "peki ne zamana kadar", "Mühendislik Fakültesi", "Lisans", q1)
    assert feedback_handler(k, q2, "Yanlış", " takip sorusu ").startswith("Kaydedildi")
    assert feedback_handler(k, None, "Doğru", "") == "Önce bir soru sorun."
    assert feedback_handler(k, q2, None, "") == "Bir seçenek işaretleyin."
    rows = [json.loads(line) for line in (tmp_path / "k.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["tur"] for r in rows] == ["soru", "soru", "degerlendirme"]
    assert rows[0]["birim"] == "muhendislik-fakultesi" and rows[0]["gosterilen"] == ["eoy:md19"]
    assert rows[0]["corpus_version"] == "2026.10.2" and rows[1]["onceki_id"] == q1
    assert (rows[2]["id"], rows[2]["karar"], rows[2]["not"]) == (q2, "yanlis", "takip sorusu")


def test_ask_handler_survives_llm_errors_and_logs_them(tmp_path):
    from yonetmelik_asistani.ui.app import Kayit, ask_handler

    class Broken:
        def chat(self, messages, **kwargs):
            raise RuntimeError("bağlantı koptu")

    k = Kayit(tmp_path / "k.jsonl")
    cevap, kaynak, qid = ask_handler(AssistantService(Retriever(), Broken(), MADDELER), k, "soru",
                                     "Belirtmek istemiyorum", "Lisans", "eski")
    assert "hata" in cevap.lower() and kaynak == "" and qid == "eski"   # önceki soru bağı korunur
    row = json.loads((tmp_path / "k.jsonl").read_text(encoding="utf-8"))
    assert row["tur"] == "hata" and "bağlantı koptu" in row["hata"]


def test_without_kayit_nothing_is_written(tmp_path):
    from yonetmelik_asistani.ui.app import Kayit, ask_handler

    s = AssistantService(Retriever(), LLM(v3(RET_CUMLESI)), MADDELER)
    cevap, _, _ = ask_handler(s, Kayit(None), "yurt ücreti", "Belirtmek istemiyorum", "Lisans", None)
    assert "kayıt" not in cevap and list(tmp_path.iterdir()) == []
