"""İndeks kurulumu: python -m yonetmelik_asistani.index [--no-dense]

BM25 her zaman (CPU) kurulur; BGE-M3 vektörleri ve Qdrant için GPU önerilir (Colab T4).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from yonetmelik_asistani.config import load_config
from yonetmelik_asistani.index.bm25 import BM25Index
from yonetmelik_asistani.retrieval.service import index_dir, load_chunks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.index")
    ap.add_argument("--no-dense", action="store_true", help="yalnızca BM25 kur (GPU gerekmez)")
    args = ap.parse_args(argv)

    cfg = load_config()
    chunks = list(load_chunks(cfg).values())
    out = index_dir(cfg)
    bm = cfg.section("retrieval").get("bm25", {})
    t0 = time.perf_counter()
    BM25Index.build([c["chunk_id"] for c in chunks], [c["text"] for c in chunks],
                    tokenizer=bm.get("tokenizer", "prefix5"), k1=bm.get("k1", 1.2),
                    b=bm.get("b", 0.75)).save(out / "bm25")
    print(f"BM25 ({bm.get('tokenizer', 'prefix5')}): {len(chunks)} parça, {time.perf_counter() - t0:.1f} sn")

    if not args.no_dense:
        from yonetmelik_asistani.index.dense import BGEM3Embedder, QdrantStore

        e = cfg.section("embedding")
        emb = BGEM3Embedder(e.get("model", "BAAI/bge-m3"), e.get("dtype", "float16"), e.get("batch_size", 16))
        t0 = time.perf_counter()
        vectors = emb.encode([c["text"] for c in chunks])
        t_embed = time.perf_counter() - t0
        QdrantStore(out / "qdrant").rebuild(chunks, vectors)
        print(f"BGE-M3: {len(vectors)} vektör × {len(vectors[0])} boyut, {t_embed:.1f} sn → {out / 'qdrant'}")
        _gpu_report()
    (out / "build.json").write_text(json.dumps(
        {"corpus_version": cfg.corpus_version, "parca": len(chunks), "dense": not args.no_dense,
         "bm25_tokenizer": bm.get("tokenizer", "prefix5")}, ensure_ascii=False), encoding="utf-8")
    return 0


def _gpu_report() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            print(f"GPU belleği (en yüksek): {torch.cuda.max_memory_allocated() / 2**30:.2f} GB")
    except ImportError:
        pass


if __name__ == "__main__":
    sys.exit(main())
