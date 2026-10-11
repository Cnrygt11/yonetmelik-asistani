"""Türkçe BM25 indeksi (plan 5.1 adım 2).

Kök bulma yöntemi yapılandırılabilir; hangisinin kullanılacağına altın set karar verir (plan 7.3):
  * prefix5 : kelimenin ilk 5 harfi (F5). Türkçe bilgi erişiminde basit ama güçlü bir yöntem.
  * snowball: Snowball Türkçe kök bulucu. Mevzuat dilinde tutarsız ("kaydı"→"ka", "izin"→"iz").
  * char    : 3-5 harflik karakter n-gramları; ek ve ünsüz yumuşaması (kayıt/kaydı) farkına dayanıklı.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yonetmelik_asistani.ingest.normalize import turkish_lower

# bm25s içe aktarılırken (selection.py) kuruluysa bir JAX işlemi çalıştırır; Colab'da JAX hazır
# kurulu gelir ve GPU'yu ilk kullanımda belleğin %75'ini ayırır (T4'te ~11 GiB, 12.10.2026).
# Biz JAX kullanmıyoruz (skorlar numpy ile seçilir), bu yüzden JAX işlemciyle sınırlanır.
os.environ.setdefault("JAX_PLATFORMS", "cpu")

_WORD_RE = re.compile(r"[0-9a-zçğıöşüâîû]+")
STOPWORDS = frozenset(["acaba", "ama", "ancak", "bazı", "belki", "ben", "bir", "biri", "birkaç", "birçok", "biz", "bu", "bunu", "bunun", "buna", "da", "daha", "de", "defa", "diye", "en", "gibi", "hem", "hep", "her", "hiç", "için", "ile", "ise", "işte", "kadar", "ki", "kim", "mı", "mi", "mu", "mü", "nasıl", "ne", "neden", "nerede", "niçin", "o", "olan", "olarak", "olduğu", "olması", "olup", "onun", "ona", "sadece", "siz", "şey", "şu", "tüm", "ve", "veya", "ya", "yani", "yine", "yoksa", "çok", "göre"])


def _words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(turkish_lower(text)) if w not in STOPWORDS]


def _prefix5(text: str) -> list[str]:
    return [w[:5] for w in _words(text)]


def _snowball(text: str) -> list[str]:
    import snowballstemmer

    return snowballstemmer.stemmer("turkish").stemWords(_words(text))


def _char(text: str) -> list[str]:
    grams: list[str] = []
    for w in _words(text):
        padded = f"_{w}_"
        for n in (3, 4, 5):
            grams += [padded[i:i + n] for i in range(len(padded) - n + 1)]
    return grams


TOKENIZERS: dict[str, Callable[[str], list[str]]] = {
    "prefix5": _prefix5, "snowball": _snowball, "char": _char,
}


@dataclass
class BM25Index:
    tokenizer: str
    ids: list[str]
    _model: object

    @classmethod
    def build(cls, ids: list[str], texts: list[str], *, tokenizer: str = "prefix5",
              k1: float = 1.2, b: float = 0.75) -> BM25Index:
        import bm25s

        tok = TOKENIZERS[tokenizer]
        model = bm25s.BM25(k1=k1, b=b)
        model.index([tok(t) for t in texts], show_progress=False)  # kendi belirteçlerimiz
        return cls(tokenizer, list(ids), model)

    def search(self, query: str, k: int = 30) -> list[tuple[str, float]]:
        import numpy as np

        vocab = self._model.vocab_dict
        tokens = [t for t in TOKENIZERS[self.tokenizer](query) if t in vocab]  # bilinmeyenler atlanır
        if not tokens:
            return []
        scores = self._model.get_scores(tokens)
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top if scores[i] > 0]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._model.save(str(directory / "model"))
        (directory / "meta.json").write_text(
            json.dumps({"tokenizer": self.tokenizer, "ids": self.ids}, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path) -> BM25Index:
        import bm25s

        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        return cls(meta["tokenizer"], meta["ids"], bm25s.BM25.load(str(directory / "model")))
