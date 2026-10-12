"""Öğrenci dili sözlüğüyle sorgu genişletme (FR-10, K-12).

Soru, sözlükteki öğrenci ifadelerinden birini içeriyorsa karşılık gelen mevzuat terimleri soruya
eklenir: "tek ders sınavına kimler girebiliyor" → "... (ek sınav)". Genişletilmiş soru BM25'e,
BGE-M3'e ve reranker'a aynı biçimde verilir. Eşleşme Türkçe karaktere duyarsızdır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from yonetmelik_asistani.ingest.normalize import ascii_fold, turkish_lower


def _norm(text: str) -> str:
    return ascii_fold(turkish_lower(text))


@dataclass(frozen=True)
class Entry:
    ifadeler: tuple[str, ...]
    terimler: tuple[str, ...]
    pattern: re.Pattern


def _pattern(ifadeler: list[str]) -> re.Pattern:
    parts = []
    for ifade in sorted({_norm(i) for i in ifadeler}, key=len, reverse=True):
        tail = r"(?![0-9a-z])" if len(ifade) <= 3 else ""  # kısa ifade yalnızca tam kelime ("af" ≠ "afet")
        parts.append(r"(?<![0-9a-z])" + re.escape(ifade) + tail)
    return re.compile("|".join(parts))


@dataclass
class Glossary:
    entries: list[Entry]

    @classmethod
    def load(cls, path: Path) -> Glossary:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
        return cls([Entry(tuple(e["ifadeler"]), tuple(e["terimler"]), _pattern(e["ifadeler"])) for e in raw])

    def matches(self, query: str) -> list[Entry]:
        q = _norm(query)
        return [e for e in self.entries if e.pattern.search(q)]

    def expand(self, query: str) -> tuple[str, list[str]]:
        """(genişletilmiş soru, eklenen terimler). Soruda zaten geçen terim tekrar eklenmez."""
        q = _norm(query)
        added: list[str] = []
        for e in self.matches(query):
            for t in e.terimler:
                if _norm(t) not in q and t not in added:
                    added.append(t)
        return (f"{query} ({'; '.join(added)})" if added else query), added
