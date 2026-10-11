"""Maddeleri arama parçalarına (chunk) böler ve metadata ekler (plan 6.4, 6.5).

  * Arama birimi fıkradır. Kısa maddeler (`short_madde_tokens` altı) bölünmez.
  * Bağlam birimi maddedir: her parça `madde_id` ile maddesine bağlanır; cevap üretilirken
    maddenin tamamı verilir (small-to-big).
  * Çok uzun fıkralar (ör. 2547 md. 54) bent gruplarına bölünür; her grubun başına fıkranın giriş
    cümlesi eklenir. Tablolar bölünmez.
  * Her parçanın başında "Belge › Bölüm › Madde n (başlık) › Fıkra k" yolu bulunur; hem BM25
    hem embedding bu yolu görür.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from yonetmelik_asistani.chunking.parser import Fikra, Madde, ParsedDoc
from yonetmelik_asistani.ingest.extract import BENT_RE
from yonetmelik_asistani.ingest.manifest import Belge

CHARS_PER_TOKEN = 4.0  # BGE-M3 (XLM-R) Türkçede ~3,5-4,5 karakter/token; kaba ama tutarlı


def approx_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class Chunk:
    chunk_id: str  # "buu-onlisans-lisans-eoy:md19:f1" veya ":md19" (bölünmemiş madde)
    madde_id: str  # "buu-onlisans-lisans-eoy:md19"
    doc_id: str
    text: str  # başlık yolu + gövde (indekslenen metin)
    body: str  # yalnızca gövde
    madde_no: int
    madde_key: str
    fikra_no: int | None
    parca: int | None  # uzun fıkra bölündüyse 1, 2, ...
    meta: dict

    def to_json(self) -> dict:
        return asdict(self)


def _doc_meta(b: Belge, corpus_version: str) -> dict:
    son = b.degisiklikler[-1] if b.degisiklikler else None
    return {
        "doc_title": b.baslik, "doc_type": b.tur, "hiyerarsi": b.hiyerarsi, "birim": b.birim,
        "duzey": b.duzey, "oncelik": b.oncelik, "durum": b.durum,
        "yayim": {"tarih": b.yayim.tarih.isoformat(), "rg_sayi": b.yayim.sayi} if b.yayim else None,
        "son_degisiklik": {"tarih": son.tarih.isoformat(), "rg_sayi": son.sayi} if son else None,
        "corpus_version": corpus_version,
    }


def _path(b: Belge, m: Madde, fikra: int | None) -> str:
    parts = [b.baslik]
    if m.bolum:
        parts.append(m.bolum)
    label = ("Geçici Madde " if m.gecici else "Madde ") + m.key.lstrip("GE")
    parts.append(f"{label} ({m.baslik})" if m.baslik else label)
    if fikra is not None:
        parts.append(f"Fıkra {fikra}")
    return " › ".join(parts)


def _split_long_fikra(f: Fikra, max_tokens: int) -> list[str]:
    """Bent sınırlarından gruplara böler; her grubun başına giriş satırı(ları) eklenir."""
    intro: list[str] = []
    units: list[list[str]] = []  # her bent, altındaki satırlar ve tablolarla birlikte bir birim
    for line in f.lines:
        if BENT_RE.match(line):
            units.append([line])
        elif units:
            units[-1].append(line)
        else:
            intro.append(line)
    if not units:  # bentsiz uzun paragraf: cümlelerden böl
        return _split_sentences(f.text, max_tokens)
    head = "\n".join(intro)
    if approx_tokens(head) > max_tokens // 2:  # giriş metni de uzunsa kendi başına parça olur
        pieces, head = _split_sentences(head, max_tokens), ""
    else:
        pieces = []
    groups: list[list[list[str]]] = [[]]
    for unit in units:
        candidate = "\n".join([head, *_flat(groups[-1]), *unit])
        if groups[-1] and approx_tokens(candidate) > max_tokens:
            groups.append([])
        groups[-1].append(unit)
    for g in groups:
        text = "\n".join([head, *_flat(g)]).strip()
        # tek bent bile sığmıyorsa cümlelerden böl; her parçanın başında giriş kalır
        if approx_tokens(text) > max_tokens and not any(ln.startswith("|") for ln in text.split("\n")):
            body = "\n".join(_flat(g))
            budget = max_tokens - approx_tokens(head)
            pieces += [f"{head}\n{p}".strip() for p in _split_sentences(body, max(budget, max_tokens // 2))]
        else:
            pieces.append(text)
    return pieces


def _flat(units: list[list[str]]) -> list[str]:
    return [line for unit in units for line in unit]


_SENTENCE_END_RE = re.compile(r"(?<=[.;:])\s+(?=[A-ZÇĞİÖŞÜ(\d])")


def _split_sentences(text: str, max_tokens: int) -> list[str]:
    """Metni cümle sınırlarından max_tokens'ı aşmayan parçalara böler (tablolar hariç)."""
    sentences = [s for line in text.split("\n") for s in _SENTENCE_END_RE.split(line) if s]
    out: list[str] = [""]
    for s in sentences:
        if out[-1] and approx_tokens(out[-1] + " " + s) > max_tokens:
            out.append("")
        out[-1] = f"{out[-1]} {s}".strip()
    return out


def _chunk(b: Belge, m: Madde, madde_id: str, meta: dict, body: str, fikra: int | None,
           parca: int | None, tekrar: int) -> Chunk:
    suffix = f":f{fikra}" if fikra is not None else ""
    suffix += f"-{tekrar}" if tekrar > 1 else ""
    suffix += f":p{parca}" if parca else ""
    extra: dict = {"tablo": any(line.startswith("|") for line in body.split("\n"))}
    if tekrar > 1:
        extra["numaralandirma_notu"] = f"resmî metinde ({fikra}) numaralı fıkra birden fazla"
    return Chunk(
        chunk_id=f"{madde_id}{suffix}", madde_id=madde_id, doc_id=b.id,
        text=f"{_path(b, m, fikra)}\n{body}", body=body, madde_no=m.no, madde_key=m.key,
        fikra_no=fikra, parca=parca, meta={**meta, **extra},
    )


def _madde_meta(b: Belge, m: Madde, doc_meta: dict) -> dict:
    kaynak_url = next((k.url for k in b.kaynaklar if k.url), None)
    if kaynak_url is None and b.kaynaklar:
        kaynak_url = f"https://kms.kaysis.gov.tr/Home/Goster/{b.kaynaklar[0].id}"
    return {**doc_meta, "bolum": m.bolum, "madde_basligi": m.baslik, "gecici": m.gecici,
            "dusuk_oncelik": m.dusuk_oncelik, "degisiklik_notlari": m.notlar,
            "atiflar": [f"{b.id}:md{n}" for n in m.atiflar()], "kaynak_url": kaynak_url}


def _fikra_texts(m: Madde) -> list[tuple[int | None, str]]:
    """(fıkra no, metin); ilk fıkra madde başlığı ve "MADDE n –" satırıyla başlar."""
    fikralar = m.fikralar or [Fikra(None, [])]
    single = len(fikralar) == 1
    out = []
    for idx, f in enumerate(fikralar):
        # numarasız paragraflar (kanunlar) sırasıyla numaralanır; tek fıkralı madde numarasız kalır
        fikra_no = None if single else (f.no if f.no is not None else idx + 1)
        text = f.text
        if idx == 0:
            text = f"{m.head} {text}".strip()
            if m.baslik:
                text = f"{m.baslik}\n{text}"
        out.append((fikra_no, text))
    return out


def chunk_document(b: Belge, doc: ParsedDoc, corpus_version: str, *,
                   short_madde_tokens: int = 350, max_tokens: int = 450) -> tuple[list[Chunk], list[dict]]:
    """(arama parçaları, madde kayıtları) döndürür. Madde kayıtları bağlam derlemede kullanılır."""
    doc_meta = _doc_meta(b, corpus_version)
    chunks: list[Chunk] = []
    maddeler: list[dict] = []
    for m in doc.maddeler:
        if b.maddeler and (m.gecici or m.key.startswith("E") or m.no not in b.maddeler):
            continue
        madde_id = f"{b.id}:md{m.key}"
        meta = _madde_meta(b, m, doc_meta)
        maddeler.append({"madde_id": madde_id, "doc_id": b.id, "madde_key": m.key,
                         "text": m.text, "path": _path(b, m, None), "meta": meta})
        if approx_tokens(m.text) <= short_madde_tokens:
            chunks.append(_chunk(b, m, madde_id, meta, m.text, None, None, 1))
            continue
        seen: dict[int, int] = {}  # resmî metinde aynı fıkra numarası iki kez geçebilir
        for fikra_no, text in _fikra_texts(m):
            parts = (_split_long_fikra(Fikra(None, text.split("\n")), max_tokens)
                     if approx_tokens(text) > max_tokens else [text])
            tekrar = 1
            if fikra_no is not None:
                seen[fikra_no] = tekrar = seen.get(fikra_no, 0) + 1
            for p, part in enumerate(parts, 1):
                chunks.append(_chunk(b, m, madde_id, meta, part, fikra_no,
                                     p if len(parts) > 1 else None, tekrar))
    return chunks, maddeler
