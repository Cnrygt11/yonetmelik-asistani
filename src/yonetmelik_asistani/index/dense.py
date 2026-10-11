"""BGE-M3 yoğun vektörleri ve Qdrant deposu (plan 5.1 adım 3, 5.3).

Modeller yalnızca kullanıldıklarında yüklenir; böylece CPU'daki birim testleri torch gerektirmez.
T4 bf16 desteklemediği için modeller fp16 çalışır (plan 7.2).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

COLLECTION = "parcalar"
PAYLOAD_KEYS = ("doc_id", "madde_id", "durum", "duzey", "birim", "hiyerarsi", "dusuk_oncelik")


class Embedder(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass
class BGEM3Embedder:
    model_name: str = "BAAI/bge-m3"
    dtype: str = "float16"
    batch_size: int = 16
    max_seq_length: int = 1024  # en uzun parça ~510 token; boşa bellek ayırma
    _model: object = None

    def _load(self):
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
            if device == "cuda" and self.dtype == "float16":
                self._model.half()  # sürümden bağımsız fp16
            self._model.max_seq_length = self.max_seq_length
        return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._load().encode(list(texts), batch_size=self.batch_size,
                                   normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


@dataclass
class CrossEncoderReranker:
    model_name: str = "BAAI/bge-reranker-v2-m3"
    dtype: str = "float16"
    batch_size: int = 8
    max_length: int = 1024
    _model: object = None

    def _load(self):
        if self._model is None:
            import torch
            from sentence_transformers import CrossEncoder

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = CrossEncoder(self.model_name, device=device, max_length=self.max_length)
            if device == "cuda" and self.dtype == "float16":
                self._model.model.half()
            if device == "cuda":
                free, total = torch.cuda.mem_get_info()
                print(f"[reranker] GPU boş {free / 2**30:.1f} / {total / 2**30:.1f} GiB, "
                      f"PyTorch ayrılmış {torch.cuda.memory_allocated() / 2**30:.1f} GiB", file=sys.stderr)
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """0-1 arası alaka skorları (tek etiketli modelde varsayılan aktivasyon sigmoid'dir)."""
        if not passages:
            return []
        model, pairs, batch = self._load(), [(query, p) for p in passages], self.batch_size
        while True:
            try:
                scores = model.predict(pairs, batch_size=batch, show_progress_bar=False)
                return [float(s) for s in scores]
            except RuntimeError as e:  # torch.OutOfMemoryError, RuntimeError'ın alt sınıfı
                if "out of memory" not in str(e).lower() or batch == 1:
                    raise
                if "torch" in sys.modules:
                    sys.modules["torch"].cuda.empty_cache()
                batch //= 2
                self.batch_size = batch
                print(f"[reranker] GPU belleği yetmedi, yığın boyu {batch}", file=sys.stderr)


class QdrantStore:
    """Yerel dosya modunda Qdrant; pilot/kalıcı yayında aynı API sunucuya bağlanır."""

    def __init__(self, path: Path | None = None, url: str | None = None) -> None:
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url) if url else QdrantClient(path=str(path))

    def rebuild(self, chunks: Sequence[dict], vectors: Sequence[Sequence[float]]) -> None:
        from qdrant_client import models

        if self.client.collection_exists(COLLECTION):
            self.client.delete_collection(COLLECTION)
        self.client.create_collection(
            COLLECTION, vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE)
        )
        points = [models.PointStruct(id=i, vector=list(v), payload=payload_of(c))
                  for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))]
        self.client.upsert(COLLECTION, points=points, wait=True)

    def search(self, vector: Sequence[float], k: int, profile: dict | None = None) -> list[tuple[str, float]]:
        hits = self.client.query_points(COLLECTION, query=list(vector), limit=k,
                                        query_filter=qdrant_filter(profile), with_payload=["chunk_id"]).points
        return [(h.payload["chunk_id"], float(h.score)) for h in hits]


def payload_of(chunk: dict) -> dict:
    meta = chunk["meta"]
    out = {"chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"], "madde_id": chunk["madde_id"]}
    out.update({k: meta[k] for k in PAYLOAD_KEYS if k in meta})
    return out


def qdrant_filter(profile: dict | None):
    """Yürürlükteki parçalar; profil verilmişse öğrenim düzeyi ve birim filtresi (FR-04)."""
    from qdrant_client import models

    must = [models.FieldCondition(key="durum", match=models.MatchValue(value="yururlukte"))]
    if profile and profile.get("duzey"):
        must.append(models.FieldCondition(key="duzey", match=models.MatchAny(any=[profile["duzey"]])))
    if profile and profile.get("birim"):
        must.append(models.FieldCondition(key="birim", match=models.MatchAny(any=["tum", profile["birim"]])))
    return models.Filter(must=must)
