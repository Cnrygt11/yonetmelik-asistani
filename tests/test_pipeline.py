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


def test_check_answer_labels_refusal_and_mixed():
    ctx = [ContextItem("K1", "h", "t")]
    ok = check_answer("10 iş günü içinde başvurulur [K1].", ctx)
    assert (ok["ret"], ok["etiket_hatalari"], ok["etiketsiz"], ok["karma"]) == (False, [], False, False)
    assert check_answer("Bkz. [K3].", ctx)["etiket_hatalari"] == ["K3"]
    assert check_answer("Başvuru gerekir.", ctx)["etiketsiz"] is True
    assert check_answer(RET_CUMLESI + " Öğrenci işlerine başvurun.", ctx)["ret"] is True
    karma = check_answer("Dört yıl üst üste ödememe gerekir [K1]. " + RET_CUMLESI, ctx)
    assert karma["ret"] and karma["karma"]                       # istem kuralı 4'e aykırı


def test_relative_rerank_filter_keeps_top_and_close_sources():
    hits = [Hit("eoy:md19:f1", "eoy:md19", 0.9, {"rerank": 0.89}),
            Hit("kanun:md44:f1", "kanun:md44", 0.5, {"rerank": 0.0098})]
    assert [c.madde_id for c in build_context(hits, CHUNKS, MADDELER)] == ["eoy:md19"]
    low = [Hit("eoy:md19:f1", "eoy:md19", 0.9, {"rerank": 0.0125}),
           Hit("kanun:md44:f1", "kanun:md44", 0.5, {"rerank": 0.004})]  # hepsi düşük: göreli eşik
    assert len(build_context(low, CHUNKS, MADDELER)) == 2


def test_header_marks_unit_specific_and_repealed_references():
    from yonetmelik_asistani.generation.pipeline import Repealed

    maddeler = {"tip:md5": {"path": "Tıp Yönergesi › Madde 5", "text": "Devam %80.",
                            "meta": {"doc_type": "birim_yonergesi", "birim": ["tip-fakultesi"]}},
                "eoy:md20": {"path": "EÖY › Madde 20", "text": "18/8/2012 tarihli ve 28388 sayılı Resmî Gazete'de",
                             "meta": {"doc_type": "kurum_yonetmeligi", "birim": ["tum"]}}}
    chunks = {"tip:md5": {"text": "x\nDevam %80."}, "eoy:md20": {"text": "x\n28388"}}
    rep = [Repealed("Öğrenci Disiplin Yönetmeliği", "2023-03-11 (RG 32129)", "2547 sayılı Kanun", ("28388",))]
    ctx = build_context([Hit("tip:md5", "tip:md5", 1), Hit("eoy:md20", "eoy:md20", 1)], chunks, maddeler,
                        repealed=rep)
    assert "[Yalnızca: tip-fakultesi]" in ctx[0].header and "[Birim yönergesi]" in ctx[0].header
    assert "UYARI" in ctx[1].header and "2547 sayılı Kanun" in ctx[1].header


def test_numbers_covered():
    from yonetmelik_asistani.generation.pipeline import numbers_covered

    assert numbers_covered("en geç 10 iş günü, en çok 4 yarıyıl", "10 iş günü içinde [K1]") == 0.5
    assert numbers_covered("sayı yok", "x") is None


def test_score_answers_metrics():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
    from score_answers import auto_atif, score

    def row(qid, gold, cevap, kaynak="whatsapp", kat="tek_madde"):
        return {"id": qid, "altin_maddeler": gold, "cevap": cevap, "kaynak": kaynak, "kategori": kat,
                "kaynaklar": [{"etiket": "K1", "madde_id": "eoy:md19"}, {"etiket": "K2", "madde_id": "eoy:md10"}]}

    rows = [row("a", ["eoy:md19"], "10 gün [K1]."), row("b", ["eoy:md19"], "Yanlış madde [K2]."),
            row("c", [], "Bulamadım.", kat="cevapsiz")]
    assert auto_atif(rows[0]) is True and auto_atif(rows[1]) is False and auto_atif(rows[2]) is None
    res = score(rows, {"a": {"karar": "dogru"}, "b": {"karar": "kismen"}, "c": {"karar": "dogru"}})
    h = res["hepsi"]
    assert (h["dogru_cevap"], h["kismen"], h["dogru_atif"], h["dogru_ret"]) == (0.5, 0.5, 0.5, 1.0)
