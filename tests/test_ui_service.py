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


def test_service_returns_only_cited_sources_and_passes_profile():
    r = Retriever()
    s = AssistantService(r, LLM("10 iş günü içinde başvurulur [K1]."), MADDELER)
    res = s.ask("kaydımı dondurmak istiyorum", birim="muhendislik-fakultesi", duzey="lisans")
    assert [k["etiket"] for k in res.kaynaklar] == ["K1"]
    assert r.profiles[-1] == {"birim": "muhendislik-fakultesi", "duzey": "lisans"}
    md = render_sources(res.kaynaklar)
    assert "İzinli ayrılma" in md and "kms.kaysis.gov.tr" in md


def test_service_refusal_has_no_sources_and_empty_question():
    s = AssistantService(Retriever(), LLM(RET_CUMLESI), MADDELER)
    res = s.ask("yurt ücreti ne kadar")
    assert res.ret and res.kaynaklar == []
    assert s.ask("   ").cevap == "Lütfen bir soru yazın."
