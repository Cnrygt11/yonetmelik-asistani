"""Türkçe karakter geri getirme: Türkçe karaktersiz yazılmış soruyu belgelerdeki yazıma yaklaştırır.

Öğrenciler sık sık Türkçe karaktersiz yazar ("sinavina", "donem"; geliştirme setinin %28'i). BM25
karakterleri zaten katlar, ama BGE-M3 ve reranker katlanmış metinde zayıflar (FAZ_4.md: sy-050'de
md. 17 BM25'te 1. sırada, reranker sonrası ilk 20'nin dışında).

Harita belgelerin kendi kelimelerinden çıkarılır: katlanmış biçim → belgelerde en sık geçen yazım.
Yalnızca Türkçe karakter içermeyen kelimelere dokunulur; belgelerde geçmeyen kelime ("kacirirsa")
olduğu gibi kalır. Kelimenin tamamı belgelerde yoksa belgelerde geçen en uzun başı (en az 5 harf)
düzeltilir, eki olduğu gibi kalır ("secimi" → "seçim" + "i"). Kısa kelimeler (mi, on), belirsiz
biçimler ("dis": diş/dış) ve belgelerde büyük harfle geçen kısaltmalar ("yok" ≠ YÖK) değiştirilmez.
Düzeltilmiş soru yalnızca BGE-M3 ve reranker'a gider; BM25 ve dil modeli özgün soruyu alır.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from yonetmelik_asistani.ingest.normalize import ascii_fold, turkish_lower

_WORD_RE = re.compile(r"\w+")
MIN_LEN = 3  # daha kısa kelimeler (mi, mu, on) değiştirilmez
MIN_PAY = 0.8  # en sık yazım, o katlanmış biçimin geçişlerinin en az bu kadarı olmalı
MIN_KOK = 5  # kelime başıyla düzeltmede en kısa baş ("disi" → "dışı" ile "disipline" bozulmasın)
# Karaktersiz hâli de geçerli bir gündelik kelime olup belgelerde başka bir kelimeye denk gelenler
# (sözlük olmadan genel kuralla ayırt edilemez): "yani" ≠ "yanı" ("yanı sıra").
KORUNAN = frozenset({"yani"})


@dataclass
class Deasciifier:
    forms: dict[str, str] = field(default_factory=dict)  # katlanmış biçim → belgelerdeki yazım

    @classmethod
    def from_texts(cls, texts: Iterable[str]) -> Deasciifier:
        counts: dict[str, Counter] = defaultdict(Counter)
        caps: Counter = Counter()  # tamamı büyük harfle geçişler (kısaltma: YÖK, ÖSYM, AKTS)
        for text in texts:
            for w in _WORD_RE.findall(text):
                low = turkish_lower(w)
                counts[ascii_fold(low)][low] += 1
                if len(w) > 1 and w.isupper():
                    caps[low] += 1
        forms = {}
        for key, c in counts.items():
            best, n = c.most_common(1)[0]
            if (best != key and len(key) >= MIN_LEN and key not in KORUNAN and n >= MIN_PAY * sum(c.values())
                    and caps[best] < n / 2):
                forms[key] = best
        return cls(forms)

    def restore(self, text: str) -> str:
        def fix(m: re.Match) -> str:
            w = m.group(0)
            low = turkish_lower(w)
            if ascii_fold(low) != low:  # zaten Türkçe karakterli
                return w
            rep = self.forms.get(low)
            if rep is None:  # tamamı belgelerde yoksa belgelerde geçen en uzun baş + ek
                n = next((n for n in range(len(low) - 1, MIN_KOK - 1, -1) if low[:n] in self.forms), None)
                if n is None:
                    return w
                rep = self.forms[low[:n]] + low[n:]
            if w[:1].isupper():
                rep = ("İ" if rep[0] == "i" else rep[0].upper()) + rep[1:]
            return rep

        return _WORD_RE.sub(fix, text)
