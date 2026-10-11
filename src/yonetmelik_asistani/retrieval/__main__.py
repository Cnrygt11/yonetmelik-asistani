"""Arama komut satırı aracı (Faz 2 çıktısı).

    python -m yonetmelik_asistani.retrieval "Kaydımı nasıl dondururum?" [--mode bm25] [--duzey lisans]
"""

from __future__ import annotations

import argparse
import sys

from yonetmelik_asistani.config import load_config
from yonetmelik_asistani.retrieval.hybrid import MODES
from yonetmelik_asistani.retrieval.service import load_retriever


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.retrieval")
    ap.add_argument("soru")
    ap.add_argument("--mode", choices=MODES, default="hybrid_rerank")
    ap.add_argument("--duzey", help="onlisans | lisans | lisansustu | hazirlik")
    ap.add_argument("--birim", help="ör. tip-fakultesi")
    ap.add_argument("-k", type=int, default=6)
    args = ap.parse_args(argv)

    cfg = load_config()
    needs_dense = args.mode != "bm25"
    retriever = load_retriever(cfg, dense=needs_dense, rerank=args.mode == "hybrid_rerank")
    profile = {"duzey": args.duzey, "birim": args.birim}
    for i, h in enumerate(retriever.search(args.soru, profile=profile, mode=args.mode, k=args.k), 1):
        chunk = retriever.chunks[h.chunk_id]
        path, _, body = chunk["text"].partition("\n")
        print(f"[{i}] {h.score:.4f}  {h.chunk_id}  {h.izler}")
        print(f"    {path}")
        print(f"    {' '.join(body.split())[:220]}…\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
