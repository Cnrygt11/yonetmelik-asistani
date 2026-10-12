from datetime import date

from yonetmelik_asistani.chunking.chunker import _split_sentences, approx_tokens, chunk_document
from yonetmelik_asistani.chunking.parser import parse_document
from yonetmelik_asistani.ingest.extract import RGRef
from yonetmelik_asistani.ingest.manifest import Belge, Kaynak

DOC = """BURSA ULUDAĞ ÜNİVERSİTESİ ÖRNEK YÖNETMELİĞİ
BİRİNCİ BÖLÜM
Amaç, Kapsam ve Tanımlar
Amaç
MADDE 1 – (1) Bu Yönetmeliğin amacı esasları düzenlemektir.
Tanımlar
MADDE 2 – (Değişik:RG-18/8/2024-32636)
(1) Bu Yönetmelikte geçen;
a) AKTS: Avrupa Kredi Transfer Sistemini,
b) GANO: Genel akademik not ortalamasını,
ifade eder.
İKİNCİ BÖLÜM
Eğitim-Öğretim
İzinli ayrılma
MADDE 3 – (1) Öğrencilere izin verilebilir. Bu Yönetmeliğin 2 nci maddesindeki tanımlar uygulanır.
(2) (Değişik:RG-18/8/2024-32636) İkinci fıkra.
(2) Resmî metinde yinelenen fıkra numarası.
Yürürlük
MADDE 4 – (1) Bu Yönetmelik yayımı tarihinde yürürlüğe girer.
Azami süre
GEÇİCİ MADDE 1 – (1) Geçici hüküm; 2547 sayılı Kanunun 44 üncü maddesi uygulanır."""


def _belge(**kw) -> Belge:
    base = {"id": "ornek", "baslik": "Örnek Yönetmelik", "tur": "kurum_yonetmeligi", "hiyerarsi": 3,
            "oncelik": "P1", "durum": "yururlukte", "duzey": ["lisans"],
            "yayim": RGRef(date(2020, 9, 20), 31250), "degisiklikler": [RGRef(date(2024, 8, 18), 32636)],
            "kaynaklar": [Kaynak(tur="kaysis", id=1)]}
    base.update(kw)
    return Belge(**base)


def test_parser_structure():
    doc = parse_document("ornek", DOC)
    assert doc.baslik == "BURSA ULUDAĞ ÜNİVERSİTESİ ÖRNEK YÖNETMELİĞİ"
    assert [m.key for m in doc.maddeler] == ["1", "2", "3", "4", "G1"]
    m2 = doc.madde("2")
    assert m2.baslik == "Tanımlar" and m2.bolum == "BİRİNCİ BÖLÜM – Amaç, Kapsam ve Tanımlar"
    assert m2.head == "MADDE 2 – (Değişik:RG-18/8/2024-32636)"  # madde düzeyinde not
    assert [f.no for f in m2.fikralar] == [1]
    assert m2.fikralar[0].lines[-1] == "ifade eder."
    m3 = doc.madde("3")
    assert m3.bolum == "İKİNCİ BÖLÜM – Eğitim-Öğretim" and [f.no for f in m3.fikralar] == [1, 2, 2]
    assert m3.notlar == ["(Değişik:RG-18/8/2024-32636)"]
    assert doc.madde("4").dusuk_oncelik and doc.madde("G1").gecici


def test_internal_vs_external_references():
    doc = parse_document("ornek", DOC)
    assert doc.madde("3").atiflar() == [2]  # "Bu Yönetmeliğin 2 nci maddesi"
    assert doc.madde("G1").atiflar() == []  # "2547 sayılı Kanunun 44 üncü maddesi" dış atıf


def test_short_articles_stay_whole_and_carry_metadata():
    chunks, maddeler = chunk_document(_belge(), parse_document("ornek", DOC), "2026.10.1")
    ids = [c.chunk_id for c in chunks]
    assert "ornek:md1" in ids and len(ids) == len(set(ids))
    c = next(c for c in chunks if c.chunk_id == "ornek:md3")
    assert c.text.startswith("Örnek Yönetmelik › İKİNCİ BÖLÜM – Eğitim-Öğretim › Madde 3 (İzinli ayrılma)\n")
    assert c.meta["atiflar"] == ["ornek:md2"]
    assert c.meta["son_degisiklik"] == {"tarih": "2024-08-18", "rg_sayi": 32636}
    assert c.meta["kaynak_url"] == "https://kms.kaysis.gov.tr/Home/Goster/1"
    assert {m["madde_id"] for m in maddeler} == {f"ornek:md{k}" for k in ("1", "2", "3", "4", "G1")}


def test_long_articles_split_by_fikra_with_duplicate_numbers_disambiguated():
    long_doc = DOC.replace("(2) (Değişik:RG-18/8/2024-32636) İkinci fıkra.",
                           "(2) (Değişik:RG-18/8/2024-32636) " + "Uzun bir cümle. " * 120)
    chunks, _ = chunk_document(_belge(), parse_document("ornek", long_doc), "v")
    m3 = [c for c in chunks if c.madde_id == "ornek:md3"]
    ids = [c.chunk_id for c in m3]
    assert ids[0] == "ornek:md3:f1" and "ornek:md3:f2-2" in ids
    assert all(approx_tokens(c.body) <= 450 for c in m3)
    assert m3[0].body.startswith("İzinli ayrılma\nMADDE 3 – (1)")  # ilk fıkra başlık + MADDE ile
    dup = next(c for c in m3 if c.chunk_id == "ornek:md3:f2-2")
    assert "birden fazla" in dup.meta["numaralandirma_notu"]


def test_long_bent_list_keeps_intro_in_every_part():
    bents = "\n".join(f"{chr(97 + i)}) " + "Bent açıklaması uzun bir metin. " * 12 for i in range(8))
    doc = DOC.replace("(1) Öğrencilere izin verilebilir.", "(1) Aşağıdaki hallerde izin verilir:\n" + bents)
    chunks, _ = chunk_document(_belge(), parse_document("ornek", doc), "v")
    parts = [c for c in chunks if c.chunk_id.startswith("ornek:md3:f1")]
    assert len(parts) > 1 and all("Aşağıdaki hallerde izin verilir:" in p.body for p in parts)


def test_law_selects_only_listed_articles():
    law = ("YÜKSEKÖĞRETİM KANUNU\nKapsam:\nMadde 2 – Bu kanun kapsar.\nÖğrenim süresi:\n"
           "Madde 44 – (Değişik: 13/2/2011-6111/171 md.)\na. Öğrenciler mezun olur.\n"
           "Disiplin:\nMadde 54 – (1) Disiplin cezaları.\nGeçici Madde 54- Geçici.\n"
           "Geçici Madde 85- Öğrenim affı.")
    _chunks, maddeler = chunk_document(_belge(id="kanun", tur="kanun", maddeler=["44", "54", "G85"]),
                                      parse_document("kanun", law), "v")
    assert [m["madde_key"] for m in maddeler] == ["44", "54", "G85"]  # geçici md. 54 seçilmedi
    assert maddeler[2]["meta"]["gecici"] is True
    assert maddeler[2]["meta"]["bolum"] == "Geçici Maddeler"  # son bölüme bağlanmaz
    assert maddeler[0]["meta"]["degisiklik_notlari"] == ["(Değişik: 13/2/2011-6111/171 md.)"]


def test_split_sentences_respects_budget():
    parts = _split_sentences("Birinci cümle. " * 200, 100)
    assert len(parts) > 1 and all(approx_tokens(p) <= 100 for p in parts)
