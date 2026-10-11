"""Soru → arama → bağlam → cevap (plan 5.1 adım 6-7). Faz 4'ün ilk, yalın sürümü.

Bağlam derleme kuralı (küçükten büyüğe): arama fıkra düzeyinde yapılır; bulunan parçanın maddesi
`madde_tokens` sınırının altındaysa maddenin tamamı, değilse yalnızca bulunan parçalar bağlama girer.
Aynı maddeden gelen parçalar tek kaynak etiketinde toplanır. Bütçe dolunca eklemek durur.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from yonetmelik_asistani.generation.prompts import RET_CUMLESI, ContextItem, build_messages
from yonetmelik_asistani.retrieval.hybrid import Hit

_LABEL_RE = re.compile(r"\[K(\d+)\]")


def approx_tokens(text: str) -> int:
    return len(text) // 4


def load_maddeler(processed_dir: Path) -> dict[str, dict]:
    with (processed_dir / "maddeler.jsonl").open(encoding="utf-8") as f:
        return {m["madde_id"]: m for m in map(json.loads, f)}


def _header(madde: dict) -> str:
    meta = madde["meta"]
    notes = meta.get("degisiklik_notlari") or []
    return madde["path"] + (f" · {'; '.join(notes)}" if notes else "")


def build_context(hits: list[Hit], chunks: dict[str, dict], maddeler: dict[str, dict], *,
                  budget: int = 5000, madde_tokens: int = 1200) -> list[ContextItem]:
    order: list[str] = []
    parts: dict[str, list[str]] = {}
    for h in hits:
        if h.madde_id not in parts:
            order.append(h.madde_id)
            parts[h.madde_id] = []
        parts[h.madde_id].append(h.chunk_id)

    items: list[ContextItem] = []
    used = 0
    for mid in order:
        madde = maddeler[mid]
        if approx_tokens(madde["text"]) <= madde_tokens:
            text = madde["text"]
        else:  # uzun madde (ör. 2547 md. 44): yalnızca bulunan fıkralar, belgedeki sırayla
            ids = sorted(parts[mid], key=lambda c: list(chunks).index(c))
            text = "\n".join(chunks[c]["text"].partition("\n")[2] for c in ids)
        cost = approx_tokens(text)
        if items and used + cost > budget:
            break
        items.append(ContextItem(f"K{len(items) + 1}", _header(madde), text))
        used += cost
    return items


@dataclass
class Answer:
    soru: str
    cevap: str
    kaynaklar: list[dict]
    ret: bool
    etiket_hatalari: list[str] = field(default_factory=list)  # bağlamda olmayan [K#]
    etiketsiz: bool = False  # ret değilse ve hiç kaynak etiketi yoksa
    ilk_rerank: float | None = None
    sure_s: float | None = None
    model: str | None = None


def check_answer(text: str, context: list[ContextItem]) -> tuple[bool, list[str], bool]:
    labels = {c.label for c in context}
    used = {f"K{n}" for n in _LABEL_RE.findall(text)}
    ret = RET_CUMLESI in text
    return ret, sorted(used - labels), (not ret and not used)


def answer(question: str, retriever, llm, maddeler: dict[str, dict], *, profile: dict | None = None,
           budget: int = 5000) -> Answer:
    hits = retriever.search(question, profile=profile, mode="hybrid_rerank")
    context = build_context(hits, retriever.chunks, maddeler, budget=budget)
    profile = profile or {}
    messages = build_messages(question, context, duzey=profile.get("duzey") or "belirtilmedi",
                              birim=profile.get("birim") or "belirtilmedi")
    result = llm.chat(messages)
    ret, bad, unlabeled = check_answer(result.text, context)
    return Answer(
        soru=question, cevap=result.text, ret=ret, etiket_hatalari=bad, etiketsiz=unlabeled,
        kaynaklar=[{"etiket": c.label, "baslik": c.header, "token": approx_tokens(c.text)} for c in context],
        ilk_rerank=hits[0].izler.get("rerank") if hits else None,
        sure_s=round(result.wall_s, 1), model=result.model,
    )
