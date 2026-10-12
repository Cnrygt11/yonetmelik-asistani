"""Aday dökümü (Faz 4, Adım 1; Colab/GPU, LLM gerekmez).

    python eval/dump_candidates.py --out eval/reports/adaylar_gelistirme.jsonl
    python eval/dump_candidates.py --out eval/reports/adaylar_gelistirme.jsonl --turkce-karakter ikisi
        # → adaylar_gelistirme_tr_acik.jsonl ve adaylar_gelistirme_tr_kapali.jsonl (karşılaştırma)

Her soru için cevap üretiminde kullanılan aramanın (profil + sözlük + hybrid_rerank) ilk `--k`
parçasını skorlarıyla (rerank, RRF, BM25 ve dense sıra/skorları) yazar; varsayılan 30, yani
reranker'ın skorladığı adayların tamamı. Bağlam derleme ayarları (kaç parça, eşikler, bağlantılı
maddeler, en çok kaynak) bu dosya üzerinde yerelde, modeli yeniden çalıştırmadan taranır:
eval/sweep_context.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_gold

from yonetmelik_asistani.config import load_config
from yonetmelik_asistani.retrieval.deasciify import Deasciifier
from yonetmelik_asistani.retrieval.service import load_retriever


def dump(out: Path, subset: list[dict], retriever, k: int, meta: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i, g in enumerate(subset, 1):
            hits = retriever.search(g["soru"], profile=g.get("profil"), mode="hybrid_rerank", k=k)
            row = {"id": g["id"], "kategori": g["kategori"], "kaynak": g.get("kaynak", "ilk"),
                   "altin_maddeler": g["altin_maddeler"], "profil": g.get("profil"),
                   "sozluk": retriever.last_expansion, "sorgu_tr": retriever.last_neural_query,
                   "adaylar": [{"chunk_id": h.chunk_id, "madde_id": h.madde_id, "skor": round(h.score, 4),
                                "izler": h.izler} for h in hits]}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if i % 20 == 0 or i == len(subset):
                print(f"[{out.stem} {i}/{len(subset)}]", flush=True)
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", choices=["gelistirme", "test", "hepsi"], default="gelistirme")
    ap.add_argument("--k", type=int, default=30)
    ap.add_argument("--turkce-karakter", choices=["ayar", "acik", "kapali", "ikisi"], default="ayar",
                    help="Türkçe karakter geri getirme; ikisi: iki döküm (_tr_acik, _tr_kapali)")
    args = ap.parse_args(argv)

    cfg = load_config()
    subset = [g for g in load_gold() if args.split == "hepsi" or g["bolum"] == args.split]
    retriever = load_retriever(cfg)
    restorer = retriever.restorer or Deasciifier.from_texts(c.get("body") or c["text"]
                                                            for c in retriever.chunks.values())
    runs = {"ayar": [(args.out, retriever.restorer)],
            "acik": [(args.out, restorer)],
            "kapali": [(args.out, None)],
            "ikisi": [(args.out.with_name(f"{args.out.stem}_tr_acik.jsonl"), restorer),
                      (args.out.with_name(f"{args.out.stem}_tr_kapali.jsonl"), None)]}[args.turkce_karakter]
    for out, rest in runs:
        retriever.restorer = rest
        meta = {"tarih": datetime.now().isoformat(timespec="seconds"), "corpus_version": cfg.corpus_version,
                "split": args.split, "k": args.k, "soru": len(subset), "turkce_karakter": rest is not None}
        dump(out, subset, retriever, args.k, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
