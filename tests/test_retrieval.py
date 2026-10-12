import pytest

from yonetmelik_asistani.index.bm25 import BM25Index, _char, _prefix5
from yonetmelik_asistani.retrieval.hybrid import HybridRetriever, matches_profile, rrf


def _chunk(cid, text, **meta):
    base = {"durum": "yururlukte", "duzey": ["onlisans", "lisans"], "birim": ["tum"], "dusuk_oncelik": False}
    base.update(meta)
    return cid, {"chunk_id": cid, "madde_id": cid.rsplit(":f", 1)[0], "text": text, "meta": base}


CHUNKS = dict([
    _chunk("eoy:md19:f2", "İzinli ayrılma: öğrencilere toplam dört yarıyıl izin verilebilir."),
    _chunk("eoy:md18", "Devam zorunluluğu: kuramsal derslere yüzde 70 devam zorunludur."),
    _chunk("eoy:md45", "Yürürlük: bu yönetmelik yayımı tarihinde yürürlüğe girer.", dusuk_oncelik=True),
    _chunk("tip:md5", "Tıp fakültesinde devam zorunluluğu yüzde 80.", birim=["tip-fakultesi"]),
    _chunk("lu:md3", "Lisansüstü öğrencilerin izin süresi.", duzey=["lisansustu"]),
])


class FakeStore:
    """Belirli bir sırayı döndüren vektör deposu; profil filtresini gerçek kuralla uygular."""

    def __init__(self, order):
        self.order = order

    def search(self, vector, k, profile=None):
        ids = [c for c in self.order if matches_profile(CHUNKS[c]["meta"], profile)]
        return [(c, 1.0 - i * 0.1) for i, c in enumerate(ids[:k])]


class FakeEmbedder:
    def encode(self, texts):
        return [[0.0] for _ in texts]


class FakeReranker:
    def __init__(self, prefer):
        self.prefer = prefer

    def score(self, query, passages):
        return [0.9 if self.prefer in p else 0.1 for p in passages]


def _retriever(**kw):
    bm25 = BM25Index.build(list(CHUNKS), [c["text"] for c in CHUNKS.values()])
    return HybridRetriever(chunks=CHUNKS, bm25=bm25, store=FakeStore(list(CHUNKS)[::-1]),
                           embedder=FakeEmbedder(), **kw)


def test_rrf_rewards_agreement():
    fused = dict(rrf([["a", "b", "c"], ["b", "a", "d"]], k=60))
    assert fused["a"] == fused["b"] > fused["c"] > 0
    assert fused["c"] == pytest.approx(1 / 63) and fused["d"] == pytest.approx(1 / 63)


def test_profile_filter():
    m = CHUNKS["tip:md5"]["meta"]
    assert matches_profile(m, None) and matches_profile(m, {"birim": "tip-fakultesi"})
    assert not matches_profile(m, {"birim": "muhendislik-fakultesi"})
    assert matches_profile(CHUNKS["eoy:md18"]["meta"], {"birim": "muhendislik-fakultesi"})  # "tum"
    assert not matches_profile(CHUNKS["lu:md3"]["meta"], {"duzey": "lisans"})
    assert not matches_profile({"durum": "kaldirildi"}, None)


def test_bm25_turkish_prefix_matches_inflections():
    assert _prefix5("Kayıt dondurma İZİNLİ") == ["kayit", "dondu", "izinl"]  # Türkçe karakter katlanır
    assert "_ka" in _char("kayıt")
    hits = _retriever().search("izinli ayrılmak istiyorum", mode="bm25")
    assert hits[0].chunk_id == "eoy:md19:f2" and "bm25" in hits[0].izler


def test_hybrid_fuses_both_lists_and_traces_stages():
    hits = _retriever().search("devam zorunluluğu yüzde kaç", mode="hybrid", k=5)
    ids = [h.chunk_id for h in hits]
    assert "eoy:md18" in ids
    top = next(h for h in hits if h.chunk_id == "eoy:md18")
    assert set(top.izler) == {"bm25", "dense"}


def test_profile_applies_to_both_searches():
    hits = _retriever().search("devam zorunluluğu", profile={"birim": "muhendislik-fakultesi"},
                               mode="hybrid", k=10)
    assert "tip:md5" not in [h.chunk_id for h in hits]


def test_reranker_decides_final_order_and_low_priority_is_penalised():
    r = _retriever(reranker=FakeReranker(prefer="Yürürlük"), low_priority_factor=0.5)
    hits = r.search("yönetmelik ne zaman yürürlüğe girer", mode="hybrid_rerank", k=3)
    top = next(h for h in hits if h.chunk_id == "eoy:md45")
    assert top.score == pytest.approx(0.45)  # 0.9 × 0.5
    assert top.izler["rerank"] == 0.9


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        _retriever().search("x", mode="sihirli")


def test_reranker_halves_batch_on_oom():
    from yonetmelik_asistani.index.dense import CrossEncoderReranker

    class FakeModel:
        def predict(self, pairs, batch_size, show_progress_bar):
            if batch_size > 2:
                raise RuntimeError("CUDA out of memory. Tried to allocate 490.00 MiB")
            return [0.5] * len(pairs)

    rr = CrossEncoderReranker(batch_size=8, _model=FakeModel())
    assert rr.score("soru", ["a", "b", "c"]) == [0.5, 0.5, 0.5]
    assert rr.batch_size == 2  # sonraki çağrılar küçük yığınla başlar


def test_bm25_module_keeps_jax_off_gpu():
    import os

    import yonetmelik_asistani.index.bm25  # noqa: F401

    assert os.environ.get("JAX_PLATFORMS") == "cpu"


def test_bm25_treats_unaccented_query_like_accented():
    ids = ["a", "b"]
    texts = ["Öğrenciler sınavlara girmek için devam koşulunu sağlamalıdır.", "Yurt ücretleri."]
    for tok in ("prefix5", "char"):
        ix = BM25Index.build(ids, texts, tokenizer=tok)
        assert ix.search("ogrenci sinavlara icin devam", k=1)[0][0] == "a"
        assert _prefix5("için sınav") == _prefix5("icin sinav") == ["sinav"]  # "icin" de durak sözcük


def test_glossary_expands_student_terms_accent_insensitive(tmp_path):
    from yonetmelik_asistani.retrieval.glossary import Glossary

    path = tmp_path / "g.yaml"
    path.write_text("- ifadeler: [tek ders]\n  terimler: [ek sınav]\n"
                    "- ifadeler: [harç, harcımı]\n  terimler: [katkı payı]\n"
                    "- ifadeler: [af]\n  terimler: [ilişiği kesilenler]\n", encoding="utf-8")
    g = Glossary.load(path)
    assert g.expand("tek ders sinavina kimler girer") == ("tek ders sinavina kimler girer (ek sınav)", ["ek sınav"])
    assert g.expand("harcimi ödemezsem")[1] == ["katkı payı"]          # Türkçe karaktersiz yazım
    assert g.expand("deprem afetinde izin")[1] == []                     # kısa ifade yalnızca tam kelime
    assert g.expand("katkı payı ve harç")[1] == []                       # soruda geçen terim tekrar eklenmez


def test_retriever_uses_expanded_query():
    class Expander:
        def expand(self, q):
            return q + " izinli ayrılma", ["izinli ayrılma"]

    r = _retriever()
    r.expander = Expander()
    hits = r.search("kaydımı dondurmak istiyorum", mode="bm25")
    assert r.last_expansion == ["izinli ayrılma"] and hits[0].chunk_id == "eoy:md19:f2"


def test_deasciifier_restores_from_document_vocabulary_only():
    from yonetmelik_asistani.retrieval.deasciify import Deasciifier

    d = Deasciifier.from_texts(["Mazeret sınavına girmek için dönem sonunda başvurulur.",
                                "Diş Hekimliği; dış kurum; sınavına; ön koşul; on iş günü."])
    assert d.restore("mazeret sinavina donem sonu") == "mazeret sınavına dönem sonu"
    assert d.restore("Donem kacirirsa") == "Dönem kacirirsa"           # belgelerde yoksa dokunulmaz
    assert d.restore("dis on mi") == "dis on mi"                       # belirsiz (diş/dış) ve kısa kelimeler
    assert d.restore("sınavına donem") == "sınavına dönem"             # karışık yazım: yalnızca karaktersiz kelime
    k = Deasciifier.from_texts(["YÖK onayı ile YÖK kararı; yanı sıra yanı sıra."])
    assert k.restore("yok yani onayi") == "yok yani onayı"             # kısaltma ve korunan kelime
    e = Deasciifier.from_texts(["Ders seçim haftası; dışı ve dışı."])
    assert e.restore("secimi disipline") == "seçimi disipline"         # bilinen baş + ek; kısa baş kullanılmaz


def test_restorer_feeds_only_neural_components():
    from yonetmelik_asistani.retrieval.hybrid import HybridRetriever

    seen = {}

    class BM25:
        def search(self, q, k=30):
            seen["bm25"] = q
            return [("c1", 1.0)]

    class Store:
        def search(self, v, k, profile=None):
            return [("c1", 0.9)]

    class Emb:
        def encode(self, texts):
            seen["dense"] = texts[0]
            return [[0.0]]

    class Rer:
        def score(self, q, passages):
            seen["rerank"] = q
            return [0.5] * len(passages)

    class Rest:
        def restore(self, t):
            return t.replace("sinav", "sınav")

    chunks = {"c1": {"madde_id": "m1", "text": "x", "meta": {}}}
    r = HybridRetriever(chunks=chunks, bm25=BM25(), store=Store(), embedder=Emb(), reranker=Rer(), restorer=Rest())
    r.search("sinav")
    assert seen == {"bm25": "sinav", "dense": "sınav", "rerank": "sınav"} and r.last_neural_query == "sınav"
