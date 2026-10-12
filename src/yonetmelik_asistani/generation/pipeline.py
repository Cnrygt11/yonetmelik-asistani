"""Soru → arama → bağlam → cevap (plan 5.1 adım 6-7). Faz 4, sürüm 2.

Bağlam derleme kuralları:
  * Küçükten büyüğe: arama fıkra düzeyinde; maddesi `madde_tokens` altındaysa maddenin tamamı,
    değilse yalnızca bulunan parçalar bağlama girer. Aynı maddenin parçaları tek kaynakta toplanır.
  * Göreli eşik: reranker skoru en iyi kaynağın `rel_rerank` katının altındaki kaynaklar atılır
    (en iyi kaynak her zaman kalır). Mutlak eşik kullanılmaz: gerçek sorularda cevabı olan
    soruların yarısında en iyi skor 0,46'nın altında (FAZ_4.md).
  * Başlıkta belge türü, değişiklik notları, "Yalnızca: <birim>" ve kaldırılmış metne atıf uyarısı.
Bütçe dolunca eklemek durur.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from yonetmelik_asistani.generation.prompts import (
    EKSIK_CUMLESI,
    RET_CUMLESI,
    ContextItem,
    build_messages,
)
from yonetmelik_asistani.ingest.normalize import ascii_fold, turkish_lower
from yonetmelik_asistani.retrieval.hybrid import Hit

_LABEL_RE = re.compile(r"\[K(\d+)\]")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")

TUR_ADI = {"kanun": "Kanun", "yok_yonetmeligi": "YÖK yönetmeliği", "kurum_yonetmeligi": "Yönetmelik",
           "senato_yonergesi": "Senato yönergesi", "birim_yonergesi": "Birim yönergesi",
           "usul_esas": "Usul ve esaslar"}


def approx_tokens(text: str) -> int:
    return len(text) // 4


def _norm(text: str) -> str:
    return ascii_fold(turkish_lower(" ".join(text.split())))


def load_maddeler(processed_dir: Path) -> dict[str, dict]:
    with (processed_dir / "maddeler.jsonl").open(encoding="utf-8") as f:
        return {m["madde_id"]: m for m in map(json.loads, f)}


@dataclass(frozen=True)
class Repealed:
    """Yürürlükten kaldırılmış bir metin ve ona atfı tanıyan kalıplar (RG sayısı, başlık)."""
    baslik: str
    kaldirilma: str
    yerine: str
    patterns: tuple[str, ...]


def load_repealed(manifest_path: Path) -> list[Repealed]:
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    titles = {b["id"]: b["baslik"] for b in data.get("belgeler", [])}
    out = []
    for k in data.get("kaldirilmis", []):
        kal = k.get("kaldirilma") or {}
        pats = [_norm(k["baslik"])]
        if (k.get("yayim") or {}).get("rg_sayi"):
            pats.append(str(k["yayim"]["rg_sayi"]))
        out.append(Repealed(k["baslik"], f"{kal.get('tarih', '?')} (RG {kal.get('rg_sayi', '?')})",
                            titles.get(k.get("yonlendir", ""), k.get("yonlendir", "")), tuple(pats)))
    return out


def repealed_refs(text: str, repealed: list[Repealed]) -> list[Repealed]:
    t = _norm(text)
    if "yururlukten kaldirilmistir" in t:  # kaldıran maddenin kendisi (ör. EÖY md. 44) atıf değildir
        return []
    return [r for r in repealed if any(p in t for p in r.patterns)]


def _header(madde: dict, repealed: list[Repealed]) -> str:
    meta = madde["meta"]
    parts = [madde["path"], f"[{TUR_ADI.get(meta.get('doc_type'), meta.get('doc_type', ''))}]"]
    birim = [b for b in meta.get("birim") or [] if b != "tum"]
    if birim:
        parts.append(f"[Yalnızca: {', '.join(birim)}]")
    notes = meta.get("degisiklik_notlari") or []
    if notes:
        parts.append("; ".join(notes))
    for r in repealed_refs(madde["text"], repealed):
        parts.append(f"[UYARI: bu madde {r.kaldirilma} tarihinde yürürlükten kaldırılan '{r.baslik}' "
                     f"metnine atıf yapıyor; yürürlükteki düzenleme: {r.yerine}]")
    return " · ".join(parts)


def build_context(hits: list[Hit], chunks: dict[str, dict], maddeler: dict[str, dict], *,
                  budget: int = 5000, madde_tokens: int = 1200, rel_rerank: float = 0.1,
                  repealed: list[Repealed] | None = None) -> list[ContextItem]:
    repealed = repealed or []
    scores = [h.izler.get("rerank") for h in hits]
    if hits and all(s is not None for s in scores):
        top = max(scores)
        hits = [h for i, h in enumerate(hits) if i == 0 or h.izler["rerank"] >= rel_rerank * top]

    order: list[str] = []
    parts: dict[str, list[str]] = {}
    for h in hits:
        if h.madde_id not in parts:
            order.append(h.madde_id)
            parts[h.madde_id] = []
        parts[h.madde_id].append(h.chunk_id)

    chunk_order = {c: i for i, c in enumerate(chunks)}
    items: list[ContextItem] = []
    used = 0
    for mid in order:
        madde = maddeler[mid]
        if approx_tokens(madde["text"]) <= madde_tokens:
            text = madde["text"]
        else:  # uzun madde (ör. 2547 md. 44): yalnızca bulunan fıkralar, belgedeki sırayla
            ids = sorted(parts[mid], key=chunk_order.__getitem__)
            text = "\n".join(chunks[c]["text"].partition("\n")[2] for c in ids)
        cost = approx_tokens(text)
        if items and used + cost > budget:
            break
        items.append(ContextItem(f"K{len(items) + 1}", _header(madde, repealed), text, mid))
        used += cost
    return items


def term_notes(question: str, expander) -> list[str]:
    """Sözlükte eşleşen öğrenci ifadeleri için modele verilecek notlar."""
    if expander is None or not hasattr(expander, "matches"):
        return []
    return [f"Öğrencilerin '{e.ifadeler[0]}' dediği şey yönetmeliklerde '{', '.join(e.terimler)}' olarak geçer."
            for e in expander.matches(question)]


@dataclass
class Answer:
    soru: str
    cevap: str
    kaynaklar: list[dict]
    ret: bool
    karma: bool = False  # ret cümlesi ile kaynak etiketi birlikte (istem kuralı 4'e aykırı)
    eksik_belirtildi: bool = False
    etiket_hatalari: list[str] = field(default_factory=list)  # bağlamda olmayan [K#]
    etiketsiz: bool = False  # ret değilse ve hiç kaynak etiketi yoksa
    terim_notlari: list[str] = field(default_factory=list)
    ilk_rerank: float | None = None
    sure_s: float | None = None
    model: str | None = None


def check_answer(text: str, context: list[ContextItem]) -> dict:
    labels = {c.label for c in context}
    used = {f"K{n}" for n in _LABEL_RE.findall(text)}
    ret = RET_CUMLESI in text
    return {"ret": ret, "karma": ret and bool(used), "eksik_belirtildi": EKSIK_CUMLESI in text,
            "etiket_hatalari": sorted(used - labels), "etiketsiz": not ret and not used}


def answer(question: str, retriever, llm, maddeler: dict[str, dict], *, profile: dict | None = None,
           budget: int = 5000, rel_rerank: float = 0.1, repealed: list[Repealed] | None = None) -> Answer:
    hits = retriever.search(question, profile=profile, mode="hybrid_rerank")
    context = build_context(hits, retriever.chunks, maddeler, budget=budget, rel_rerank=rel_rerank,
                            repealed=repealed)
    notes = term_notes(question, getattr(retriever, "expander", None))
    profile = profile or {}
    messages = build_messages(question, context, duzey=profile.get("duzey") or "belirtilmedi",
                              birim=profile.get("birim") or "belirtilmedi", terim_notlari=notes)
    result = llm.chat(messages)
    checks = check_answer(result.text, context)
    return Answer(
        soru=question, cevap=result.text, terim_notlari=notes, **checks,
        kaynaklar=[{"etiket": c.label, "madde_id": c.madde_id, "baslik": c.header, "token": approx_tokens(c.text)}
                   for c in context],
        ilk_rerank=hits[0].izler.get("rerank") if hits else None,
        sure_s=round(result.wall_s, 1), model=result.model,
    )


def numbers_covered(alinti: str | None, cevap: str) -> float | None:
    """Altın alıntıdaki sayıların cevapta geçme oranı (otomatik ön kontrol; süre ve oranlar)."""
    nums = set(_NUM_RE.findall(alinti or ""))
    if not nums:
        return None
    found = set(_NUM_RE.findall(cevap))
    return round(len(nums & found) / len(nums), 2)
