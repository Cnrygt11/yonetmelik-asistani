"""Yapılandırılmış metni Bölüm › Madde › Fıkra ağacına ayrıştırır (plan 6.4).

Girdi, ingest.extract'in ürettiği satır yapısıdır: başlık, "MADDE n –", "(k) ..." fıkra ve
"a) ..." bent satırları ayrı satırlardadır; tablolar "|" ile başlayan Markdown satırlarıdır.
Kanunlarda fıkralar numarasız paragraflar olabilir; o zaman her paragraf bir fıkra sayılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from yonetmelik_asistani.ingest.extract import BENT_RE, BOLUM_RE, FIKRA_RE, MADDE_RE

_MADDE_HEAD_RE = re.compile(
    r"^(?:(?P<gecici>GEÇİCİ|Geçici)\s+|(?P<ek>EK|Ek)\s+)?(?:MADDE|Madde)\s+"
    r"(?P<no>\d+)(?P<harf>/[A-ZÇĞİÖŞÜ])?\s*[–-]\s*"
)
_LEADING_NOTE_RE = re.compile(r"^\((?:Değişik|Mülga|Ek|İptal)[^)]*\)\s*")
NOTE_RE = re.compile(r"\((?:Değişik|Mülga|Ek|İptal)[^)]*\)")
_FIKRA_NO_RE = re.compile(r"^\((\d+)\)\s*")
# "9 uncu madde", "19 uncu maddesinin" gibi atıflar
_REF_RE = re.compile(r"(\d+)\s*(?:'?\s*)(?:inci|ıncı|uncu|üncü|nci|ncı|ncu|ncü)\s+madde", re.IGNORECASE)
# Atıftan hemen önce başka bir mevzuat adı geçiyorsa dış atıftır
_EXTERNAL_HINT_RE = re.compile(r"(sayılı|Kanunun|Kanunu|Yönetmeliğin(?!\s*$)|Yönetmelik[’']in)\s*$")
_LOW_PRIORITY_TITLES = {"yürürlük", "yürütme", "yürürlükten kaldırılan yönetmelik",
                        "yürürlükten kaldırılan yönerge"}


@dataclass
class Fikra:
    no: int | None  # numarasız paragraf (kanunlar) veya giriş satırı için None
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class Madde:
    key: str  # "19", "G2" (geçici), "E3" (ek), "53/A"
    no: int
    baslik: str | None
    bolum: str | None
    gecici: bool = False
    head: str = ""  # "MADDE 19 –" ve varsa madde düzeyindeki değişiklik notu
    fikralar: list[Fikra] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [self.baslik] if self.baslik else []
        body = "\n".join(f.text for f in self.fikralar)
        parts.append(f"{self.head} {body}".strip() if self.head and body else (self.head or body))
        return "\n".join(parts)

    @property
    def notlar(self) -> list[str]:
        """Madde içindeki değişiklik notları, tekrarsız ve sırasıyla."""
        seen: dict[str, None] = {}
        for note in NOTE_RE.findall(self.head + "\n" + "\n".join(f.text for f in self.fikralar)):
            seen.setdefault(" ".join(note.split()), None)
        return list(seen)

    @property
    def dusuk_oncelik(self) -> bool:
        return (self.baslik or "").strip().lower() in _LOW_PRIORITY_TITLES

    def atiflar(self) -> list[int]:
        """Aynı belgedeki diğer maddelere yapılan atıfların madde numaraları."""
        text = self.text
        refs: list[int] = []
        for m in _REF_RE.finditer(text):
            before = text[max(0, m.start() - 40):m.start()]
            if _EXTERNAL_HINT_RE.search(before.rstrip()) and "bu yönetmeli" not in before.lower() \
                    and "bu yönerge" not in before.lower():
                continue
            n = int(m.group(1))
            if n != self.no and n not in refs:
                refs.append(n)
        return refs


@dataclass
class ParsedDoc:
    doc_id: str
    baslik: str
    maddeler: list[Madde]

    def madde(self, key: str) -> Madde:
        return next(m for m in self.maddeler if m.key == key)


def _is_title(line: str) -> bool:
    return (len(line) <= 120 and not line.endswith((".", ",", ";"))
            and not (MADDE_RE.match(line) or FIKRA_RE.match(line) or BENT_RE.match(line)
                     or line.startswith("|")))


def parse_document(doc_id: str, text: str) -> ParsedDoc:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    preamble: list[str] = []
    maddeler: list[Madde] = []
    bolum: str | None = None
    current: Madde | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        if BOLUM_RE.match(line):
            name = nxt if nxt and not MADDE_RE.match(nxt) and _is_title(nxt) and \
                not MADDE_RE.match(lines[i + 2] if i + 2 < len(lines) else "") else ""
            bolum = f"{line} – {name}" if name else line
            i += 2 if name else 1
            continue

        if _is_title(line) and MADDE_RE.match(nxt):  # madde başlığı: bir sonraki satırda işlenir
            i += 1
            current = _start_madde(nxt, line, bolum)
            maddeler.append(current)
            i += 1
            continue

        if MADDE_RE.match(line):
            current = _start_madde(line, None, bolum)
            maddeler.append(current)
        elif current is None:
            preamble.append(line)
        elif m := _FIKRA_NO_RE.match(line):
            current.fikralar.append(Fikra(int(m.group(1)), [line]))
        elif current.fikralar:
            current.fikralar[-1].lines.append(line)
        else:
            current.fikralar.append(Fikra(None, [line]))
        i += 1

    title = " ".join(preamble[:4]) if preamble else doc_id
    return ParsedDoc(doc_id, " ".join(title.split()), maddeler)


def _start_madde(line: str, baslik: str | None, bolum: str | None) -> Madde:
    m = _MADDE_HEAD_RE.match(line)
    assert m, line
    gecici, ek = bool(m.group("gecici")), bool(m.group("ek"))
    no = int(m.group("no"))
    key = ("G" if gecici else "E" if ek else "") + m.group("no") + (m.group("harf") or "")
    head = line[: m.end()].strip()
    rest = line[m.end():]
    note = _LEADING_NOTE_RE.match(rest)
    if note:  # "MADDE 4 – (Değişik:RG-...)" madde düzeyinde not
        head = f"{head} {note.group(0).strip()}"
        rest = rest[note.end():]
    madde = Madde(key=key, no=no, baslik=baslik.strip() if baslik else None, bolum=bolum,
                  gecici=gecici, head=head)
    if rest.strip():
        fm = _FIKRA_NO_RE.match(rest)
        madde.fikralar.append(Fikra(int(fm.group(1)) if fm else None, [rest.strip()]))
    return madde
