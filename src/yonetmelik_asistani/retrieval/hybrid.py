"""Hibrit arama: BM25 + BGE-M3 → RRF → reranker (plan 5.1 adım 2-5).

Arama kipleri (karşılaştırma deneyleri için, plan 7.3):
  bm25 | dense | hybrid (RRF) | hybrid_rerank (RRF + bge-reranker-v2-m3)
Profil filtresi (FR-04) her iki aramada aynı kurallarla uygulanır: yalnızca yürürlükteki parçalar;
düzey verildiyse o düzeyi kapsayan; birim verildiyse "tum" veya o birime ait olanlar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


class _Lexical(Protocol):
    def search(self, query: str, k: int = 30) -> list[tuple[str, float]]: ...


class _VectorStore(Protocol):
    def search(self, vector: Sequence[float], k: int, profile: dict | None = None) -> list[tuple[str, float]]: ...


class _Embedder(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class _Reranker(Protocol):
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


@dataclass
class Hit:
    chunk_id: str
    madde_id: str
    score: float
    izler: dict = field(default_factory=dict)  # her aşamadaki sıra/skor (izlenebilirlik, NFR-05)


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: her listede sıra r için 1/(k+r) toplanır."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for r, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def matches_profile(meta: dict, profile: dict | None) -> bool:
    if meta.get("durum", "yururlukte") != "yururlukte":
        return False
    if profile and profile.get("duzey") and profile["duzey"] not in meta.get("duzey", []):
        return False
    return not (profile and profile.get("birim") and not ({"tum", profile["birim"]} & set(meta.get("birim", []))))


@dataclass
class HybridRetriever:
    chunks: dict[str, dict]  # chunk_id → chunk kaydı (chunks.jsonl)
    bm25: _Lexical | None = None
    store: _VectorStore | None = None
    embedder: _Embedder | None = None
    reranker: _Reranker | None = None
    candidates: int = 30
    rrf_k: int = 60
    top_n: int = 6
    low_priority_factor: float = 0.8  # "Yürürlük", "Yürütme" maddeleri (plan 6.4)

    def _lexical(self, query: str, profile: dict | None) -> list[tuple[str, float]]:
        # filtre sonrasında da yeterli aday kalsın diye fazladan getirilir
        hits = self.bm25.search(query, k=self.candidates * 3)
        return [(c, s) for c, s in hits if matches_profile(self.chunks[c]["meta"], profile)][: self.candidates]

    def _dense(self, query: str, profile: dict | None) -> list[tuple[str, float]]:
        vector = self.embedder.encode([query])[0]
        return self.store.search(vector, k=self.candidates, profile=profile)

    def search(self, query: str, profile: dict | None = None, mode: str = "hybrid_rerank",
               k: int | None = None) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"bilinmeyen kip: {mode}")
        k = k or self.top_n
        traces: dict[str, dict] = {}
        lists: list[list[str]] = []
        if mode in ("bm25", "hybrid", "hybrid_rerank"):
            lex = self._lexical(query, profile)
            lists.append([c for c, _ in lex])
            for r, (c, s) in enumerate(lex, 1):
                traces.setdefault(c, {})["bm25"] = (r, round(s, 4))
        if mode in ("dense", "hybrid", "hybrid_rerank"):
            den = self._dense(query, profile)
            lists.append([c for c, _ in den])
            for r, (c, s) in enumerate(den, 1):
                traces.setdefault(c, {})["dense"] = (r, round(s, 4))

        fused = rrf(lists, self.rrf_k) if len(lists) > 1 else [
            (c, 1.0 / (self.rrf_k + r)) for r, c in enumerate(lists[0], 1)]
        if mode == "hybrid_rerank" and self.reranker is not None and fused:
            ids = [c for c, _ in fused[: self.candidates]]
            scores = self.reranker.score(query, [self.chunks[c]["text"] for c in ids])
            ranked = list(zip(ids, scores, strict=True))
            for c, s in ranked:
                traces[c]["rerank"] = round(s, 4)
        else:
            ranked = list(fused)

        hits = []
        for c, s in ranked:
            meta = self.chunks[c]["meta"]
            factor = self.low_priority_factor if meta.get("dusuk_oncelik") else 1.0
            hits.append(Hit(c, self.chunks[c]["madde_id"], s * factor, traces.get(c, {})))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]
