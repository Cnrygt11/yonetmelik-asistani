"""Türkçe metin normalizasyonu (plan 6.6). Faz 1'de tireleme ve üst/alt bilgi temizliği eklenecek."""

from __future__ import annotations

import unicodedata

_TR_UPPER_TO_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def turkish_lower(text: str) -> str:
    """Türkçeye uygun küçük harf dönüşümü.

    `str.lower()` "I" harfini "i" yapar (doğrusu "ı") ve "İ" harfini "i" + birleşik nokta
    (U+0307) dizisine çevirir. Bu yüzden önce bu iki harf elle dönüştürülür.
    """
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_TO_LOWER).lower()


_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def ascii_fold(text: str) -> str:
    """Küçük harfli Türkçe metni Türkçe karaktersiz biçime indirir ("harcımı" → "harcimi").

    Öğrenciler sık sık Türkçe karakter kullanmadan yazar; arama iki biçimi aynı saymalıdır.
    Önce `turkish_lower` uygulanmalıdır.
    """
    return text.translate(_FOLD)
