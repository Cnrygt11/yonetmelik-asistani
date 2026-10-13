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


def test_linked_madde_follows_its_parent_and_respects_max_sources():
    maddeler = {**MADDELER, "eoy:md20": {"path": "EÖY › Madde 20", "text": "Bağlantılı kısa madde.", "meta": {}}}
    hits = [Hit("eoy:md19:f1", "eoy:md19", 0.9, {"rerank": 0.9}),
            Hit("kanun:md44:f1", "kanun:md44", 0.5, {"rerank": 0.5})]
    links = {"eoy:md19": ["eoy:md20"], "eoy:md20": ["eoy:md19"]}
    ctx = build_context(hits, CHUNKS, maddeler, links=links)
    assert [(c.madde_id, c.bagli, c.rerank) for c in ctx] == [
        ("eoy:md19", "", 0.9), ("eoy:md20", "eoy:md19", None), ("kanun:md44", "", 0.5)]
    assert [c.madde_id for c in build_context(hits, CHUNKS, maddeler, links=links, max_sources=2)] == [
        "eoy:md19", "eoy:md20"]
    # parçası bulunmamış uzun madde bağlantıyla eklenmez
    assert [c.madde_id for c in build_context(hits[:1], CHUNKS, MADDELER, links={"eoy:md19": ["kanun:md44"]})] == [
        "eoy:md19"]


def test_load_links_reads_repo_file():
    from yonetmelik_asistani.config import REPO_ROOT
    from yonetmelik_asistani.generation.pipeline import load_links

    links = load_links(REPO_ROOT / "configs" / "ilgili_maddeler.yaml")
    assert "buu-onlisans-lisans-eoy:md35" in links["buu-onlisans-lisans-eoy:md32"]


def test_verify_quote_tolerates_case_punctuation_and_ellipsis_but_not_invention():
    from yonetmelik_asistani.generation.pipeline import verify_quote

    ctx = [ContextItem("K1", "h", "(1) Mazeret hâlinde, sınavdan sonraki 10 iş günü içinde başvurulur."),
           ContextItem("K2", "h", "(2) Kayıt dondurma en çok 4 yarıyıldır.")]
    assert verify_quote("mazeret halinde sinavdan sonraki 10 is gunu icinde basvurulur", "K1", ctx) == "K1"
    assert verify_quote("Mazeret hâlinde … 10 iş günü içinde başvurulur.", "K1", ctx) == "K1"
    assert verify_quote("Kayıt dondurma en çok 4 yarıyıldır.", "K1", ctx) == "K2"  # yanlış etiket düzeltilir
    assert verify_quote("Kayıt dondurma en çok 6 yarıyıldır.", "K2", ctx) is None
    assert verify_quote("Madde 5", "K1", ctx) is None


def test_render_v3_refuses_without_verified_quote():
    import json

    from yonetmelik_asistani.generation.pipeline import render_v3

    ctx = [ContextItem("K1", "h", "Kayıt dondurma en çok 4 yarıyıldır.")]
    ok = json.dumps({"alintilar": [{"kaynak": "K1", "metin": "Kayıt dondurma en çok 4 yarıyıldır."}],
                     "cevap": "Kaydını en çok 4 yarıyıl dondurabilirsin.", "ayrintilar": ["Ek bilgi [K1]"],
                     "eksik": True})
    text, quotes, err = render_v3(ok, ctx)
    assert text.startswith("Kaydını en çok 4 yarıyıl dondurabilirsin. [K1]") and "- Ek bilgi [K1]" in text
    assert "Bu ayrıntı yönetmeliklerde yer almıyor." in text and quotes[0]["gecerli"] and not err
    uydurma = json.dumps({"alintilar": [{"kaynak": "K1", "metin": "Kayıt dondurma en çok 8 yarıyıldır."}],
                          "cevap": "8 yarıyıl [K1].", "ayrintilar": [], "eksik": False})
    assert render_v3(uydurma, ctx)[0].startswith(RET_CUMLESI)
    text, _, err = render_v3('{"alintilar": [{"kaynak": "K1", "metin": "Kayıt', ctx)  # kesik JSON
    assert text.startswith(RET_CUMLESI) and err


def test_answer_v3_sends_schema_and_logs_quotes_and_scores():
    import json
    import types

    from yonetmelik_asistani.generation.pipeline import answer

    class Retriever:
        chunks = CHUNKS
        expander = None

        def search(self, q, profile=None, mode="hybrid_rerank"):
            return [Hit("eoy:md19:f1", "eoy:md19", 0.9, {"rerank": 0.8})]

    class LLM:
        def chat(self, messages, **kw):
            self.kw = kw
            out = {"alintilar": [{"kaynak": "K1", "metin": "İzinli ayrılma (1)"}], "cevap": "İzin alınabilir [K1].",
                   "ayrintilar": [], "eksik": False}
            return types.SimpleNamespace(text=json.dumps(out, ensure_ascii=False), wall_s=2.0, model="sahte",
                                         prompt_tokens=900)

    llm = LLM()
    a = answer("izin?", Retriever(), llm, MADDELER, istem="v3", think=True, max_tokens=3000)
    assert llm.kw["schema"]["required"][0] == "alintilar" and llm.kw["think"] is True
    assert a.cevap == "İzin alınabilir [K1]." and not a.ret and a.alintilar[0]["gecerli"]
    assert a.kaynaklar[0]["rerank"] == 0.8 and a.prompt_tokens == 900 and a.istem == "v3"


def test_hit_madde_first_queued_as_link_still_brings_its_own_links():
    # md7 bulunur ve md24'ü bağlantı olarak getirir; md24 sonra aramada da çıkar: md24'ün kendi
    # bağlantısı (md23) yine eklenmeli. Yalnızca bağlantıyla gelen maddenin bağlantısı eklenmez.
    maddeler = {m: {"path": m, "text": f"{m} kısa metin.", "meta": {}} for m in ("y:md7", "y:md24", "y:md23", "y:md8")}
    chunks = {m: {"text": f"{m}\n{m} kısa metin."} for m in maddeler}
    links = {"y:md7": ["y:md24"], "y:md24": ["y:md23"], "y:md23": ["y:md8"]}
    hits = [Hit("y:md7", "y:md7", 0.9, {"rerank": 0.9}), Hit("y:md24", "y:md24", 0.8, {"rerank": 0.8})]
    ctx = build_context(hits, chunks, maddeler, links=links)
    assert [(c.madde_id, c.bagli) for c in ctx] == [("y:md7", ""), ("y:md24", ""), ("y:md23", "y:md24")]


def test_split_sentences_keeps_abbreviations_and_decimals():
    from yonetmelik_asistani.generation.pipeline import split_sentences

    t = "GANO'n 1.80'in altındaysa yeni ders alamazsın [K1]. Ayrıntı md. 27'de [K1]. (Not) son."
    assert split_sentences(t) == ["GANO'n 1.80'in altındaysa yeni ders alamazsın [K1].", "Ayrıntı md. 27'de [K1].",
                                  "(Not) son."]


def test_support_checker_drops_flagged_sentences_and_refuses_if_nothing_left():
    import json
    import types

    from yonetmelik_asistani.generation.pipeline import SupportChecker, render

    ctx = [ContextItem("K1", "h", "Yaz öğretiminde alınan dersler için bütünleme sınavı yapılmaz.")]
    raw = json.dumps({"alintilar": [{"kaynak": "K1", "metin": "Yaz öğretiminde alınan dersler için bütünleme sınavı yapılmaz."}],
                      "cevap": "Hayır, yaz okulunda büt yok [K1]. Başarısızlıkta ek sınav hakkı da tanınmaz [K1].",
                      "ayrintilar": ["Bağlamda başka bir kural yok."], "eksik": False}, ensure_ascii=False)

    class LLM:
        def __init__(self, flagged):
            self.flagged, self.seen = flagged, None

        def chat(self, messages, **kw):
            self.seen = messages[-1]["content"]
            return types.SimpleNamespace(text=json.dumps({"desteklenmeyen": self.flagged}), wall_s=1.0)

    llm = LLM([{"no": 1, "neden": "ek sınav Yaz md. 13/3'te var"}])
    text, _, err, removed = render(raw, ctx, SupportChecker(llm, ctx), sade=True)
    assert text == "Hayır, yaz okulunda büt yok [K1].\n- Yönetmeliklerde başka bir kural yok." and not err
    assert removed == [{"cumle": "Başarısızlıkta ek sınav hakkı da tanınmaz [K1].", "neden": "ek sınav Yaz md. 13/3'te var"}]
    assert "1. Başarısızlıkta ek sınav" in llm.seen and "<metinler>" in llm.seen
    hepsi = LLM([{"no": 0, "neden": "x"}, {"no": 1, "neden": "y"}])
    assert render(raw, ctx, SupportChecker(hepsi, ctx))[0].startswith(RET_CUMLESI)


def test_follow_up_question_is_rewritten_before_search():
    import json
    import types

    from yonetmelik_asistani.generation.pipeline import answer

    class Retriever:
        chunks = CHUNKS
        expander = None

        def __init__(self):
            self.queries = []

        def search(self, q, profile=None, mode="hybrid_rerank"):
            self.queries.append(q)
            return [Hit("eoy:md19:f1", "eoy:md19", 0.9, {"rerank": 0.8})]

    class LLM:
        def chat(self, messages, schema=None, **kw):
            if schema and "soru" in schema["properties"]:
                return types.SimpleNamespace(text=json.dumps({"soru": "Kaydımı dondurursam ikinci öğretimde harç öder miyim?"}),
                                             wall_s=0.5, model="sahte", prompt_tokens=1)
            out = {"alintilar": [{"kaynak": "K1", "metin": "İzinli ayrılma (1)"}], "cevap": "Evet [K1].",
                   "ayrintilar": [], "eksik": False}
            return types.SimpleNamespace(text=json.dumps(out, ensure_ascii=False), wall_s=2.0, model="sahte",
                                         prompt_tokens=9)

    r = Retriever()
    a = answer("peki ikinci öğretimde?", r, LLM(), MADDELER, gecmis=[("Kaydımı dondurursam harç öder miyim?", "…")])
    assert r.queries == ["Kaydımı dondurursam ikinci öğretimde harç öder miyim?"]
    assert a.soru == "peki ikinci öğretimde?" and a.yeniden_yazilan.startswith("Kaydımı dondurursam") and a.sure_s == 2.5
    b = answer("izin?", Retriever(), LLM(), MADDELER)          # geçmiş yoksa yeniden yazılmaz
    assert b.yeniden_yazilan == ""
