from yonetmelik_asistani.generation.pipeline import build_context, check_answer
from yonetmelik_asistani.generation.prompts import RET_CUMLESI, ContextItem
from yonetmelik_asistani.retrieval.hybrid import Hit

CHUNKS = {
    "eoy:md19:f1": {"text": "EÖY › Madde 19 › Fıkra 1\n(1) Mazeret halinde 10 iş günü içinde başvurulur."},
    "eoy:md19:f2": {"text": "EÖY › Madde 19 › Fıkra 2\n(2) Derslerden en az 10 iş günü önce başvurulur."},
    "kanun:md44:f1": {"text": "2547 › Madde 44 › Fıkra 1\n(1) Azami süre " + "x" * 100},
    "kanun:md44:f2": {"text": "2547 › Madde 44 › Fıkra 2\n(2) Ek sınav " + "y" * 100},
}
MADDELER = {
    "eoy:md19": {"path": "EÖY › Madde 19 (İzinli ayrılma)", "text": "İzinli ayrılma\n(1) ... (2) ...",
                 "meta": {"degisiklik_notlari": ["Değişik:RG-18/8/2024-32636"]}},
    "kanun:md44": {"path": "2547 › Madde 44", "text": "z" * 8000, "meta": {}},
}


def test_context_merges_fikra_hits_into_whole_short_madde():
    hits = [Hit("eoy:md19:f2", "eoy:md19", 0.9), Hit("eoy:md19:f1", "eoy:md19", 0.5)]
    ctx = build_context(hits, CHUNKS, MADDELER)
    assert len(ctx) == 1 and ctx[0].label == "K1"
    assert ctx[0].text == MADDELER["eoy:md19"]["text"]  # maddenin tamamı
    assert "Değişik:RG-18/8/2024-32636" in ctx[0].header


def test_long_madde_uses_only_hit_fikras_in_document_order():
    hits = [Hit("kanun:md44:f2", "kanun:md44", 0.9), Hit("kanun:md44:f1", "kanun:md44", 0.4)]
    ctx = build_context(hits, CHUNKS, MADDELER, madde_tokens=1200)
    assert ctx[0].text.startswith("(1) Azami süre") and "(2) Ek sınav" in ctx[0].text


def test_budget_stops_adding_sources_but_keeps_first():
    hits = [Hit("eoy:md19:f1", "eoy:md19", 0.9), Hit("kanun:md44:f1", "kanun:md44", 0.4)]
    assert [c.label for c in build_context(hits, CHUNKS, MADDELER, budget=1)] == ["K1"]


def test_check_answer_labels_and_refusal():
    ctx = [ContextItem("K1", "h", "t")]
    assert check_answer("10 iş günü içinde başvurulur [K1].", ctx) == (False, [], False)
    assert check_answer("Bkz. [K3].", ctx) == (False, ["K3"], False)
    assert check_answer("Başvuru gerekir.", ctx) == (False, [], True)
    assert check_answer(RET_CUMLESI + " Öğrenci işlerine başvurun.", ctx) == (True, [], False)
