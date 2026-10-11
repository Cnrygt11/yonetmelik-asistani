from yonetmelik_asistani.ingest.normalize import turkish_lower


def test_dotted_and_dotless_i():
    assert turkish_lower("İZİN") == "izin"
    assert turkish_lower("KAYIT") == "kayıt"
    assert turkish_lower("BULAMADIM") == "bulamadım"


def test_no_combining_dot_left():
    assert "̇" not in turkish_lower("İlişik Kesme")


def test_plain_python_lower_is_wrong_for_turkish():
    # Bu test, neden özel fonksiyona ihtiyaç olduğunu belgeler.
    assert "KAYIT".lower() != turkish_lower("KAYIT")
