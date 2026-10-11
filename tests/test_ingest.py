from datetime import date

from yonetmelik_asistani.ingest.extract import (
    KONSOLIDE,
    RG_ILK_NUSHA,
    RGRef,
    _join_structural_lines,
    build_extracted,
    count_annotations,
    parse_rg_header,
    parse_rg_table,
    split_maddeler,
)
from yonetmelik_asistani.ingest.kaysis import parse_index
from yonetmelik_asistani.ingest.manifest import Belge, Teyit, load_manifest
from yonetmelik_asistani.ingest.verify import cross_check, verify

R2020 = RGRef(date(2020, 9, 20), 31250)
R2023 = RGRef(date(2023, 3, 7), 32125)
R2024 = RGRef(date(2024, 8, 18), 32636)


# ---------------- KAYSİS listesi ----------------
def test_parse_index_assigns_sections_and_dedupes():
    page = """
    <a href="#collapse1">Kurum Yönetmelikleri 34</a>
    <a href="https://kms.kaysis.gov.tr/Home/Goster/167318">BURSA ULUDAĞ ÜNİVERSİTESİ ÖNLİSANS VE LİSANS
       EĞİTİM ÖĞRETİM YÖNETMELİĞİ</a>
    <a href="https://kms.kaysis.gov.tr/Home/Goster/167318">BURSA ULUDAĞ ÜNİVERSİTESİ ÖNLİSANS VE LİSANS</a>
    <a href="#collapse3">Yönergeler 130</a>
    <a href="https://kms.kaysis.gov.tr/Home/Goster/206796">MUAFİYET &amp; İNTİBAK</a>
    """
    docs = parse_index(page)
    assert [(d.goster_id, d.bolum) for d in docs] == [
        (167318, "Kurum Yönetmelikleri"), (206796, "Yönergeler")
    ]
    assert docs[0].baslik.endswith("EĞİTİM ÖĞRETİM YÖNETMELİĞİ")  # satır sonu birleşti
    assert docs[1].baslik == "MUAFİYET & İNTİBAK"


# ---------------- satır yapısı ----------------
def test_word_per_line_madde_is_rejoined():
    block = "Amaç \nMADDE \n1 \n– (1) \nBu \nYönetmeliğin \namacı; \nesasları düzenlemektir. \n"
    assert _join_structural_lines(block) == [
        "Amaç",
        "MADDE 1 – (1) Bu Yönetmeliğin amacı; esasları düzenlemektir.",
    ]


def test_title_fikra_and_bent_get_own_lines():
    block = ("(3) Kayıt olan aday öğrenci olur. \nYatay geçiş işlemleri \nMADDE 7 – (1) Kontenjanlar \n"
             "Senato tarafından belirlenir. \n(2) İkinci fıkra; \na) birinci bent, \nb) ikinci bent.")
    assert _join_structural_lines(block) == [
        "(3) Kayıt olan aday öğrenci olur.",
        "Yatay geçiş işlemleri",
        "MADDE 7 – (1) Kontenjanlar Senato tarafından belirlenir.",
        "(2) İkinci fıkra;",
        "a) birinci bent,",
        "b) ikinci bent.",
    ]


def test_law_style_articles_and_bolum_headings():
    lines = _join_structural_lines(
        "İKİNCİ BÖLÜM \nKayıt ile İlgili Esaslar \nÖğrencilerin disiplin işleri: \n"
        "Madde 54 – (Değişik:2/2/2023-7437/2 md.) \n(1) Disiplin cezaları:"
    )
    assert lines == [
        "İKİNCİ BÖLÜM",
        "Kayıt ile İlgili Esaslar",
        "Öğrencilerin disiplin işleri:",
        "Madde 54 – (Değişik:2/2/2023-7437/2 md.)",
        "(1) Disiplin cezaları:",
    ]


def test_title_at_block_end_belongs_to_next_madde():
    # Sayfa sonu: başlık bir bloğun son satırı, MADDE sonraki bloğun ilk satırı
    lines = _join_structural_lines(["(1) Önceki fıkra kaldırılmıştır. \nYürürlük \n",
                                    "MADDE 45 – (1) Yürürlüğe girer."])
    assert lines == ["(1) Önceki fıkra kaldırılmıştır.", "Yürürlük", "MADDE 45 – (1) Yürürlüğe girer."]


def test_sentence_continuing_on_next_page_is_joined():
    lines = _join_structural_lines(["(2) Hazırlık sınıfında başarısız \n", "olan öğrenciler devam eder."])
    assert lines == ["(2) Hazırlık sınıfında başarısız olan öğrenciler devam eder."]


def test_split_maddeler_keeps_titles_with_their_article():
    text = ("BİRİNCİ BÖLÜM\nAmaç ve Kapsam\nAmaç\nMADDE 1 – (1) Amaç.\nKapsam\nMADDE 2 – (1) Kapsar.\n"
            "İKİNCİ BÖLÜM\nKayıt\nİlk kayıt\nMADDE 3 – (1) Kayıt.\n(2) İkinci.\nGeçici hüküm\n"
            "GEÇİCİ MADDE 1 – (1) Geçici.")
    m = split_maddeler(text)
    assert list(m) == ["1", "2", "3", "G1"]
    assert m["2"] == "Kapsam\nMADDE 2 – (1) Kapsar."
    assert m["3"] == "İlk kayıt\nMADDE 3 – (1) Kayıt.\n(2) İkinci."  # bölüm başlığı karışmaz
    assert m["G1"].startswith("Geçici hüküm\n")


def test_line_end_hyphen_is_kept_without_space():
    assert _join_structural_lines("MADDE 3 – (1) eğitim-\nöğretim yılı") == [
        "MADDE 3 – (1) eğitim-öğretim yılı"
    ]


# ---------------- güncellik bilgisi ----------------
TABLE_TAIL = (
    "Yönetmeliğin Yayımlandığı Resmî Gazete’nin \nTarihi \nSayısı \n20/9/2020 \n31250 \n"
    "Yönetmelikte Değişiklik Yapan Yönetmeliklerin Yayımlandığı Resmî \n"
    "Gazetelerin \nTarihi \nSayısı \n1. \n7/3/2023 \n32125 \n2. \n18/8/2024 \n32636 \n"
)


def test_parse_rg_table():
    assert parse_rg_table(TABLE_TAIL) == (R2020, [R2023, R2024])


def test_parse_rg_header():
    assert parse_rg_header("1 Eylül 2020 SALI \nResmî Gazete \nSayı : 31231 \n") == RGRef(
        date(2020, 9, 1), 31231
    )


def test_count_annotations():
    text = ("MADDE 4 – (Değişik:RG-18/8/2024-32636) Tanımlar\n(2) (Değişik:RG-18/8/2024-32636) x\n"
            "d) (Mülga:RG-7/3/2023-32125)")
    assert count_annotations(text) == {R2024: 2, R2023: 1}


def test_konsolide_document():
    blocks = ["Tanımlar \nMADDE 4 – (Değişik:RG-18/8/2024-32636) (1) a) AKTS",
              "MADDE 18 – (3) d) (Mülga:RG-7/3/2023-32125)",
              "Yürütme \nMADDE 46 – (1) Rektör yürütür.", TABLE_TAIL]
    ex = build_extracted(blocks, pages=1)
    assert ex.bicim == KONSOLIDE and ex.yayim == R2020 and ex.degisiklikler == [R2023, R2024]
    assert "Gazetelerin" not in ex.text  # tablo metne karışmaz


def test_rg_first_print_strips_preamble():
    blocks = ["1 Eylül 2020 SALI \nResmî Gazete \nSayı : 31231 \n", "YÖNETMELİK \n",
              "Bursa Uludağ Üniversitesinden: \n", "YAZ ÖĞRETİMİ YÖNETMELİĞİ \n",
              "Amaç \nMADDE 1 – (1) Amaç."]
    ex = build_extracted(blocks, pages=1)
    assert ex.bicim == RG_ILK_NUSHA and ex.yayim == RGRef(date(2020, 9, 1), 31231)
    assert ex.text.startswith("YAZ ÖĞRETİMİ YÖNETMELİĞİ")


def test_law_header_is_not_mistaken_for_amendment_table():
    blocks = ["YÜKSEKÖĞRETİM KANUNU",
              "Kanun Numarası : 2547 \nYayımlandığı Resmî Gazete : Tarih : 6/11/1981 \nSayı : 17506",
              "Kapsam: \nMadde 2 – Bu kanun kapsar.", "Madde 54 – (1) Disiplin."]
    ex = build_extracted(blocks, pages=1)
    assert "Madde 54 – (1) Disiplin." in ex.text
    assert ex.degisiklikler == []


# ---------------- doğrulama ----------------
def _belge(**kw) -> Belge:
    base = {"id": "x", "baslik": "X", "tur": "kurum_yonetmeligi", "hiyerarsi": 3, "oncelik": "P1",
            "durum": "yururlukte", "yayim": R2020, "degisiklikler": [R2023, R2024]}
    base.update(kw)
    return Belge(**base)


def _konsolide(degisiklikler, counts):
    blocks = ["MADDE 1 – (1) x"]
    ex = build_extracted(blocks, 1)
    ex.bicim, ex.yayim, ex.degisiklikler, ex.annotation_counts = KONSOLIDE, R2020, degisiklikler, counts
    return ex


def test_verify_konsolide_ok_and_missing_amendment():
    assert verify(_belge(), _konsolide([R2023, R2024], {R2023: 1, R2024: 22})) == []
    issues = verify(_belge(), _konsolide([R2023], {R2023: 1}))
    assert any("PDF'e işlenmemiş" in i and "32636" in i for i in issues)


def test_verify_new_amendment_not_in_manifest():
    issues = verify(_belge(degisiklikler=[R2023]), _konsolide([R2023, R2024], {R2023: 1, R2024: 3}))
    assert any("manifest'te olmayan" in i for i in issues)


def test_verify_first_print_requires_fresh_confirmation():
    ex = build_extracted(["1 Eylül 2020 SALI \nResmî Gazete \nSayı : 31231", "MADDE 1 – (1) x"], 1)
    b = _belge(yayim=RGRef(date(2020, 9, 1), 31231), degisiklikler=[])
    assert any("teyit edilmeli" in i for i in verify(b, ex))

    fresh = _belge(yayim=b.yayim, degisiklikler=[], degisiklik_teyidi=Teyit(date(2026, 10, 1), ["x"]))
    assert verify(fresh, ex, today=date(2026, 10, 11)) == []
    assert any("eski" in i for i in verify(fresh, ex, today=date(2027, 6, 1)))

    stale = _belge(yayim=b.yayim, degisiklikler=[R2024], degisiklik_teyidi=Teyit(date(2026, 10, 1), ["x"]))
    assert any("eskimiş" in i for i in verify(stale, ex, today=date(2026, 10, 11)))


def test_cross_check_ignores_whitespace_and_quotes_but_reports_real_differences():
    a = "Amaç\nMADDE 1 – (1) GANO’ları en az 2.00.\nKapsam\nMADDE 2 – (1) Kapsar."
    b = "Amaç\nMADDE 1 – (1)  GANO'ları en az 2.00.\nKapsam\nMADDE 2 – (1) Kapsamaz.\nMADDE 3 – (1) Yeni."
    cc = cross_check(a, b)
    assert (cc.ortak, cc.ayni) == (2, 1)
    assert [k for k, _ in cc.farkli] == ["2"] and cc.yalniz_ikincide == ["3"]
    assert len(cc.issues) == 2


def test_directives_are_not_rg_checked():
    assert verify(_belge(tur="senato_yonergesi", yayim=None, degisiklikler=[]),
                  build_extracted(["MADDE 1 – (1) x"], 1)) == []


# ---------------- gerçek manifest ----------------
def test_real_manifest_p1_entries_have_sources():
    belgeler = load_manifest()
    p1 = [b for b in belgeler if b.oncelik == "P1"]
    assert {b.id for b in p1} >= {"buu-onlisans-lisans-eoy", "buu-yaz-ogretimi", "kanun-2547"}
    assert all(b.kaynaklar for b in p1)
    eoy = next(b for b in belgeler if b.id == "buu-onlisans-lisans-eoy")
    assert eoy.degisiklikler == [R2023, R2024]


def test_required_phrases_are_enforced():
    ex = build_extracted(["Madde 54 – (Değişik:2/2/2023-7437/2 md.) (1) Disiplin."], 1)
    ok = _belge(tur="kanun", yayim=None, degisiklikler=[], zorunlu_ifadeler=["7437/2 md."])
    missing = _belge(tur="kanun", yayim=None, degisiklikler=[], zorunlu_ifadeler=["E: 2023/78"])
    assert verify(ok, ex) == []
    assert any("2023/78" in i for i in verify(missing, ex))


def test_images_are_flagged_and_tables_render_as_markdown():
    from yonetmelik_asistani.ingest.extract import TABLE_MARK, table_markdown

    md = table_markdown([["Sınav", "Puan"], ["YDS", "60"], [None, None]])
    assert md == "| Sınav | Puan |\n|---|---|\n| YDS | 60 |"
    ex = build_extracted(["MADDE 8 – (1) Eşdeğerler:", TABLE_MARK + md, "(2) Sonraki fıkra."], 1)
    assert ex.text.split("\n") == ["MADDE 8 – (1) Eşdeğerler:", "| Sınav | Puan |", "|---|---|",
                                   "| YDS | 60 |", "(2) Sonraki fıkra."]
    ex.image_pages = [3]
    assert any("resim" in i for i in verify(_belge(tur="senato_yonergesi"), ex))


def test_wrapped_title_is_recovered_from_previous_paragraph():
    lines = _join_structural_lines(
        "(2) Yönetmelikle düzenlenir.36 Diploma alma ve öğrencilik haklarından yararlanma\n"
        "ve sınavlar:37\nMadde 44 – (Değişik: 13/2/2011-6111/171 md.)"
    )
    assert lines == ["(2) Yönetmelikle düzenlenir.",
                     "Diploma alma ve öğrencilik haklarından yararlanma ve sınavlar:37",
                     "Madde 44 – (Değişik: 13/2/2011-6111/171 md.)"]


def test_repeated_page_margin_text_is_detected():
    from yonetmelik_asistani.ingest.extract import _repeated_margin_texts

    pages = [[(10, 0, "Senato Karar Eki", True), (300, 0, "metin", False)],
             [(10, 0, "Senato  Karar Eki", True), (12, 0, "1 Eylül 2020 SALI", True)]]
    assert _repeated_margin_texts(pages) == {"Senato Karar Eki"}
