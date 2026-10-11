"""PDF'ten metin çıkarma, satır yapısını onarma ve güncellik bilgisini okuma (plan 5.2, adım 3-4).

KAYSİS'te iki tür yönetmelik PDF'i vardır:
  * İşlenmiş (konsolide) metin: sonunda "Yönetmeliğin Yayımlandığı Resmî Gazete" tablosu bulunur;
    ilk satır yayım, sonrakiler değişiklik yapan yönetmeliklerdir.
  * Resmî Gazete ilk yayım nüshası: ilk sayfada "1 Eylül 2020 SALI / Resmî Gazete / Sayı : 31231"
    başlığı vardır. Sonradan değişiklik yapıldıysa bu kopya eskimiştir; değişmediği ayrıca teyit edilir.
Ayrıca iki yana yaslı metin PyMuPDF'te kelime kelime ayrı satırlara düşebilir
("MADDE \\n1 \\n– (1) \\nBu \\nYönetmeliğin ..."); satırlar yapısal işaretlere göre yeniden birleştirilir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_ORDINALS = (
    "BİRİNCİ|İKİNCİ|ÜÇÜNCÜ|DÖRDÜNCÜ|BEŞİNCİ|ALTINCI|YEDİNCİ|SEKİZİNCİ|DOKUZUNCU|ONUNCU|"
    "ON BİRİNCİ|ON İKİNCİ|ON ÜÇÜNCÜ"
)
# Yönetmeliklerde "MADDE 19 –", kanunlarda "Madde 54 –", "Geçici Madde 54-", "Ek Madde 32 –"
MADDE_RE = re.compile(r"^(?:(?:GEÇİCİ|Geçici|EK|Ek)\s+)?(?:MADDE|Madde)\s+\d+(?:/[A-ZÇĞİÖŞÜ])?\s*[–-]")
BOLUM_RE = re.compile(rf"^(?:{_ORDINALS})\s+BÖLÜM\b")
FIKRA_RE = re.compile(r"^\(\d+\)\s")
BENT_RE = re.compile(r"^(?:[a-zçğıöşü]|\d{1,2})[).]\s")  # "a) " yönetmelik, "a. " kanun
_SPLIT_MADDE_RE = re.compile(r"((?:GEÇİCİ\s+|EK\s+)?MADDE)\s*\n\s*(\d+)\s*\n?\s*([–-])")
_MADDE_LINE_RE = re.compile(r"^\s*" + MADDE_RE.pattern[1:], re.MULTILINE)  # blok içinde satır başı
RG_TABLE_START = re.compile(r"Yayımlandığı\s+Resm[iî]\s+Gazete")
_RG_ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*\n?\s*(\d{4,5})")
ANNOTATION_RE = re.compile(
    r"\((?:Değişik|Mülga|Ek|İptal)[^)]*?RG-\s*(\d{1,2})/(\d{1,2})/(\d{4})-(\d{4,5})[^)]*\)"
)
_AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
          "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
RG_HEADER_RE = re.compile(
    rf"(\d{{1,2}})\s+({'|'.join(_AYLAR)})\s+(\d{{4}})\s+\S+\s*\n\s*Resm[iî]\s+Gazete\s*\n\s*Sayı\s*:\s*(\d{{4,5}})"
)
# İlk yayım nüshasında başlıktan sonra gelen ve yönetmelik metnine ait olmayan satırlar
_RG_PREAMBLE_RE = re.compile(r"^(?:YÖNETMELİK|.+Üniversitesinden:)$")

KONSOLIDE, RG_ILK_NUSHA, BELIRSIZ = "konsolide", "rg_ilk_nusha", "belirsiz"


@dataclass(frozen=True)
class RGRef:
    tarih: date
    sayi: int

    def __str__(self) -> str:
        return f"RG {self.tarih:%d.%m.%Y}/{self.sayi}"


@dataclass
class Extracted:
    text: str
    pages: int
    bicim: str  # KONSOLIDE | RG_ILK_NUSHA | BELIRSIZ
    yayim: RGRef | None
    degisiklikler: list[RGRef] = field(default_factory=list)
    annotation_counts: dict[RGRef, int] = field(default_factory=dict)


def parse_rg_header(block: str) -> RGRef | None:
    m = RG_HEADER_RE.search(block)
    if not m:
        return None
    d, ay, y, n = m.groups()
    return RGRef(date(int(y), _AYLAR.index(ay) + 1, int(d)), int(n))


def _join_structural_lines(blocks: str | list[str]) -> list[str]:
    """PDF bloklarının satırlarını mantıksal satırlara (başlık, madde, fıkra, bent) birleştirir.

    Bloklar tek bir akış olarak işlenir: madde başlığı bir bloğun son satırında, "MADDE" satırı
    sonraki blokta olabilir (ör. sayfa sonu). Bir blok, sayfa geçişinde devam eden bir cümle
    (küçük harfle başlayan) değilse yeni satırla başlar.
    """
    if isinstance(blocks, str):
        blocks = [blocks]
    raw: list[tuple[str, bool]] = []  # (satır, blok başı mı)
    for block in blocks:
        lines = [" ".join(ln.split()) for ln in _SPLIT_MADDE_RE.sub(r"\1 \2 \3", block).split("\n")]
        lines = [ln for ln in lines if ln]
        raw.extend((ln, j == 0 and not ln[0].islower()) for j, ln in enumerate(lines))
    out: list[str] = []
    after_bolum = False
    for i, (line, block_start) in enumerate(raw):
        next_is_madde = i + 1 < len(raw) and bool(MADDE_RE.match(raw[i + 1][0]))
        starts_new = (
            not out
            or block_start
            or MADDE_RE.match(line)
            or BOLUM_RE.match(line)
            or FIKRA_RE.match(line)
            or BENT_RE.match(line)
            or next_is_madde  # madde başlığı
            or after_bolum  # bölüm adı
        )
        if starts_new:
            out.append(line)
        elif out[-1].endswith("-"):
            out[-1] += line  # satır sonunda bölünmüş kelime: tireyi koru, boşluk ekleme
        else:
            out[-1] += " " + line
        after_bolum = bool(BOLUM_RE.match(line))
    return out


def parse_rg_table(tail: str) -> tuple[RGRef | None, list[RGRef]]:
    rows = [RGRef(date(int(y), int(m), int(d)), int(n)) for d, m, y, n in _RG_ROW_RE.findall(tail)]
    if not rows:
        return None, []
    return rows[0], rows[1:]


_MADDE_KEY_RE = re.compile(r"^(?:(GEÇİCİ|Geçici)\s+|(EK|Ek)\s+)?(?:MADDE|Madde)\s+(\d+(?:/[A-ZÇĞİÖŞÜ])?)")


def split_maddeler(text: str) -> dict[str, str]:
    """Yapılandırılmış metni maddelere böler: {"19": "...", "G2": "...", "E32": "..."}.

    Madde başlığı (MADDE satırından önceki satır) bir önceki maddeye değil, kendi maddesine aittir.
    """
    out: dict[str, list[str]] = {}
    current: str | None = None
    skip_next = False
    for line in text.split("\n"):
        if BOLUM_RE.match(line):  # bölüm başlığı ve ardındaki bölüm adı maddeye ait değildir
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        m = _MADDE_KEY_RE.match(line)
        if m:
            key = ("G" if m.group(1) else "E" if m.group(2) else "") + m.group(3)
            title = out[current].pop() if current and _is_title(out[current][-1]) else None
            current = key
            out[current] = [title] if title else []
        if current:
            out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def _is_title(line: str) -> bool:
    """Madde başlığı: kısa, fıkra/bent/madde değil ve cümle gibi noktayla bitmiyor."""
    return (len(line) <= 120 and not line.endswith(".")
            and not (MADDE_RE.match(line) or FIKRA_RE.match(line) or BENT_RE.match(line)))


def count_annotations(text: str) -> dict[RGRef, int]:
    counts: dict[RGRef, int] = {}
    for d, m, y, n in ANNOTATION_RE.findall(text):
        ref = RGRef(date(int(y), int(m), int(d)), int(n))
        counts[ref] = counts.get(ref, 0) + 1
    return counts


def structure_text(blocks: list[str]) -> tuple[str, str]:
    """Bloklardan (gövde metni, Resmî Gazete tablosu) döndürür.

    Tablo yalnızca son maddeden sonra aranır: kanunların başındaki künyede de
    "Yayımlandığı Resmî Gazete" ifadesi geçer ve orası tablo değildir.
    """
    last_madde = max(
        (i for i, b in enumerate(blocks) if _MADDE_LINE_RE.search(_SPLIT_MADDE_RE.sub(r"\1 \2 \3", b))),
        default=-1,
    )
    body_blocks: list[str] = []
    tail_parts: list[str] = []
    in_tail = False
    for i, block in enumerate(blocks):
        if not in_tail and i > last_madde and RG_TABLE_START.search(" ".join(block.split())):
            in_tail = True
        (tail_parts if in_tail else body_blocks).append(block)
    return "\n".join(_join_structural_lines(body_blocks)), "\n".join(tail_parts)


def extract_pdf(path: Path) -> Extracted:
    import pymupdf  # ağır bağımlılık; yalnızca 'ingest' ekstrasıyla kurulur

    with pymupdf.open(path) as doc:
        blocks = [
            unicodedata.normalize("NFC", b[4])
            for page in doc
            for b in page.get_text("blocks", sort=True)
            if b[6] == 0  # yalnız metin blokları
        ]
        pages = len(doc)
    return build_extracted(blocks, pages)


def build_extracted(blocks: list[str], pages: int) -> Extracted:
    header = parse_rg_header(blocks[0]) if blocks else None
    if header:
        blocks = blocks[1:]
        while blocks and _RG_PREAMBLE_RE.match(" ".join(blocks[0].split())):
            blocks = blocks[1:]
    body, tail = structure_text(blocks)
    yayim, degisiklikler = parse_rg_table(tail)
    if yayim:
        bicim = KONSOLIDE
    elif header:
        bicim, yayim = RG_ILK_NUSHA, header
    else:
        bicim = BELIRSIZ
    return Extracted(body, pages, bicim, yayim, degisiklikler, count_annotations(body))
