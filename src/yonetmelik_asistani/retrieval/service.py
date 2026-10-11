"""Arama bileşenlerini yapılandırmadan kurar (indeks dizinleri: <data_dir>/index/)."""

from __future__ import annotations

import json
from pathlib import Path

from yonetmelik_asistani.config import Config
from yonetmelik_asistani.retrieval.hybrid import HybridRetriever


def index_dir(cfg: Config) -> Path:
    return cfg.index_dir or cfg.data_dir / "index"


def load_chunks(cfg: Config) -> dict[str, dict]:
    path = cfg.data_dir / "processed" / "chunks.jsonl"
    with path.open(encoding="utf-8") as f:
        return {c["chunk_id"]: c for c in map(json.loads, f)}


def load_retriever(cfg: Config, *, dense: bool = True, rerank: bool = True) -> HybridRetriever:
    from yonetmelik_asistani.index.bm25 import BM25Index

    r = cfg.section("retrieval")
    chunks = load_chunks(cfg)
    retriever = HybridRetriever(
        chunks=chunks,
        bm25=BM25Index.load(index_dir(cfg) / "bm25"),
        candidates=r.get("bm25", {}).get("candidates", 30),
        rrf_k=r.get("rrf_k", 60),
        top_n=cfg.section("reranker").get("top_n", 6),
        low_priority_factor=r.get("low_priority_factor", 0.8),
    )
    if dense:
        from yonetmelik_asistani.index.dense import BGEM3Embedder, QdrantStore

        e = cfg.section("embedding")
        retriever.embedder = BGEM3Embedder(e.get("model", "BAAI/bge-m3"), e.get("dtype", "float16"),
                                           e.get("batch_size", 16))
        retriever.store = QdrantStore(index_dir(cfg) / "qdrant")
    if dense and rerank:
        from yonetmelik_asistani.index.dense import CrossEncoderReranker

        rr = cfg.section("reranker")
        retriever.reranker = CrossEncoderReranker(rr.get("model", "BAAI/bge-reranker-v2-m3"),
                                                  rr.get("dtype", "float16"), rr.get("batch_size", 8))
    return retriever
