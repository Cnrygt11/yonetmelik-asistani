"""Arama değerlendirmesi (plan 9.1-9.3).

    python eval/run_eval.py                       # geliştirme setinde, tüm BM25 belirteçleri
    python eval/run_eval.py --split test          # kilitli test (yalnızca kilometre taşlarında)
    python eval/run_eval.py --tokenizers prefix5  # tek yöntem
    python eval/run_eval.py --methods bm25,dense,hybrid,hybrid_rerank   # Colab/GPU; önce indeks kurulmalı

Altın set madde düzeyindedir: parçalama yöntemi değişse de geçerliliğini korur.
Recall@5: altın maddelerden en az birine ait bir parçanın ilk 5 sonuçta olması.
MRR@10  : altın maddeye ait ilk parçanın sırasının tersi (ilk 10 içinde değilse 0).
Bölünme kalıcıdır: soru kimliğinin özetine göre %30 test, %70 geliştirme.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.index.bm25 import TOKENIZERS, BM25Index

GOLD = REPO_ROOT / "eval" / "gold_set.jsonl"
REPORTS = REPO_ROOT / "eval" / "reports"


def split_of(qid: str) -> str:
    return "test" if int(hashlib.sha256(qid.encode()).hexdigest(), 16) % 10 < 3 else "gelistirme"


def load_gold(path: Path = GOLD) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        r["bolum"] = split_of(r["id"])
    return rows


def validate(gold: list[dict], maddeler: dict[str, dict]) -> list[str]:
    """Her altın maddenin var olduğunu ve alıntının o maddelerden birinde birebir geçtiğini denetler."""
    problems = []
    ids = [g["id"] for g in gold]
    if len(ids) != len(set(ids)):
        problems.append("yinelenen soru kimliği")
    for g in gold:
        missing = [m for m in g["altin_maddeler"] if m not in maddeler]
        if missing:
            problems.append(f"{g['id']}: derlemde olmayan altın madde {missing}")
            continue
        if g["altin_maddeler"] and not any(" ".join(g["alinti"].split()) in " ".join(maddeler[m]["text"].split())
                                           for m in g["altin_maddeler"]):
            problems.append(f"{g['id']}: alıntı altın maddelerde birebir geçmiyor: {g['alinti'][:60]!r}")
    return problems


def evaluate(search, gold: list[dict], madde_of: dict[str, str], k: int = 10) -> dict:
    """search(soru, k) → [(parça kimliği, skor), ...] sıralı."""
    per_q = []
    for g in gold:
        hits = search(g["soru"], k)
        ranked = [madde_of[cid] for cid, _ in hits]
        gold_set = set(g["altin_maddeler"])
        rank = next((i + 1 for i, m in enumerate(ranked) if m in gold_set), None)
        per_q.append({"id": g["id"], "kategori": g["kategori"], "cevapli": bool(gold_set),
                      "sira": rank, "ilk_skor": hits[0][1] if hits else 0.0,
                      "ilk5": ranked[:5]})
    ans = [q for q in per_q if q["cevapli"]]
    recall5 = statistics.mean(1.0 if q["sira"] and q["sira"] <= 5 else 0.0 for q in ans) if ans else None
    mrr10 = statistics.mean(1 / q["sira"] if q["sira"] else 0.0 for q in ans) if ans else None
    by_cat: dict[str, list] = defaultdict(list)
    for q in ans:
        by_cat[q["kategori"]].append(1.0 if q["sira"] and q["sira"] <= 5 else 0.0)
    unans = [q["ilk_skor"] for q in per_q if not q["cevapli"]]
    return {
        "recall@5": recall5, "mrr@10": mrr10, "cevapli": len(ans), "cevapsiz": len(unans),
        "kategori_recall@5": {c: statistics.mean(v) for c, v in sorted(by_cat.items())},
        "ilk_skor_cevapli_medyan": statistics.median(q["ilk_skor"] for q in ans) if ans else None,
        "ilk_skor_cevapsiz": unans,
        "kacirilan": [q["id"] for q in ans if not (q["sira"] and q["sira"] <= 5)],
        "sorular": per_q,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["gelistirme", "test", "hepsi"], default="gelistirme")
    ap.add_argument("--tokenizers", default=",".join(TOKENIZERS), help="bm25 kipi için")
    ap.add_argument("--methods", default="bm25", help="bm25,dense,hybrid,hybrid_rerank")
    ap.add_argument("--sozluk", choices=["acik", "kapali", "ikisi"], default="acik",
                    help="bm25 kipinde öğrenci dili sözlüğü (K-12); ikisi: karşılaştırma")
    args = ap.parse_args(argv)

    cfg = load_config()
    processed = cfg.data_dir / "processed"
    chunks = [json.loads(line) for line in (processed / "chunks.jsonl").open(encoding="utf-8")]
    maddeler = {m["madde_id"]: m for m in map(json.loads, (processed / "maddeler.jsonl").open(encoding="utf-8"))}
    gold = load_gold()
    problems = validate(gold, maddeler)
    if problems:
        print("ALTIN SET HATALI:\n  - " + "\n  - ".join(problems))
        return 1
    subset = gold if args.split == "hepsi" else [g for g in gold if g["bolum"] == args.split]
    print(f"Altın set: {len(gold)} soru (geliştirme {sum(g['bolum'] == 'gelistirme' for g in gold)}, "
          f"test {sum(g['bolum'] == 'test' for g in gold)}) · değerlendirilen: {args.split} ({len(subset)})")

    bm = cfg.section("retrieval").get("bm25", {})
    madde_of = {c["chunk_id"]: c["madde_id"] for c in chunks}
    results = {}
    methods = args.methods.split(",")
    runs = []
    from yonetmelik_asistani.retrieval.glossary import Glossary

    glossary = Glossary.load(REPO_ROOT / cfg.section("paths").get("glossary", "data/glossary.yaml"))
    if "bm25" in methods:
        for tok in args.tokenizers.split(","):
            index = BM25Index.build([c["chunk_id"] for c in chunks], [c["text"] for c in chunks],
                                    tokenizer=tok, k1=bm.get("k1", 1.2), b=bm.get("b", 0.75))
            for soz in (["kapali", "acik"] if args.sozluk == "ikisi" else [args.sozluk]):
                exp = (lambda q: q) if soz == "kapali" else (lambda q: glossary.expand(q)[0])
                name = f"bm25-{tok}" + ("+sozluk" if soz == "acik" else "")
                runs.append((name, lambda q, k, ix=index, exp=exp: ix.search(exp(q), k=k)))
    neural = [m for m in methods if m != "bm25"]
    if neural:
        from yonetmelik_asistani.retrieval.service import load_retriever

        retriever = load_retriever(cfg, dense=True, rerank="hybrid_rerank" in neural)
        expander = retriever.expander

        def neural_search(q, k, m, exp):
            retriever.expander = exp
            return [(h.chunk_id, h.score) for h in retriever.search(q, mode=m, k=k)]

        for mode in neural:
            for soz in (["kapali", "acik"] if args.sozluk == "ikisi" else [args.sozluk]):
                exp = expander if soz == "acik" else None
                runs.append((mode + ("+sozluk" if soz == "acik" else ""),
                             lambda q, k, m=mode, exp=exp: neural_search(q, k, m, exp)))
    for name, search in runs:
        try:
            r = evaluate(search, subset, madde_of)
        except RuntimeError as e:  # ör. GPU belleği; önceki kiplerin sonuçları kaybolmasın
            print(f"  {name:15} HATA: {type(e).__name__}: {str(e)[:300]}")
            results[name] = {"hata": f"{type(e).__name__}: {e}"}
            continue
        results[name] = r
        print(f"  {name:15} Recall@5 {r['recall@5']:.3f}  MRR@10 {r['mrr@10']:.3f}  "
              f"kaçırılan: {', '.join(r['kacirilan']) or '-'}")
        if r["cevapsiz"]:
            print(f"  {'':15} ilk skor medyanı: cevaplı {r['ilk_skor_cevapli_medyan']:.3f} · "
                  f"cevapsız {', '.join(f'{x:.3f}' for x in r['ilk_skor_cevapsiz'])}")
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"retrieval_{datetime.now():%Y%m%d_%H%M%S}_{args.split}.json"
    out.write_text(json.dumps({"tarih": datetime.now().isoformat(timespec="seconds"),
                               "corpus_version": cfg.corpus_version, "parca": len(chunks),
                               "split": args.split, "sonuclar": results}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"Rapor: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
