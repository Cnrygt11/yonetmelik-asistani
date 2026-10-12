"""Bağlam derleme taraması (Faz 4, Adım 1; yerelde, saniyeler sürer).

    python eval/sweep_context.py eval/reports/adaylar_gelistirme.jsonl

Aday dökümündeki (eval/dump_candidates.py) parçalar üzerinde build_context'i ayar ızgarasıyla
çalıştırır. Ayarlar: k (aramadan alınan parça), göreli ve mutlak rerank eşiği, en çok kaynak,
bağlantılı maddeler. Ölçütler (cevaplı sorularda):
  tam      : altın maddelerin tamamı bağlamda (M3: tamamı olanlarda doğruluk belirgin yüksek)
  herhangi : altın maddelerden en az biri bağlamda
  kaynak   : ortalama kaynak sayısı;  gurultu: altın olmayan kaynak sayısı;  token: bağlam boyu
Cevapsız sorularda yalnızca ortalama kaynak sayısı raporlanır (az olması reddi kolaylaştırır).
Başlangıç çizgisi M3'teki ayardır (k=6, göreli 0,1, sınır ve bağlantı yok). Pareto sınırı:
aynı ya da daha az gürültüyle daha yüksek "tam" veren başka ayar olmayanlar.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.pipeline import (
    approx_tokens,
    build_context,
    load_links,
    load_maddeler,
)
from yonetmelik_asistani.retrieval.hybrid import Hit
from yonetmelik_asistani.retrieval.service import load_chunks

IZGARA = {"k": [6, 8, 10, 12, 15, 20], "rel": [0.05, 0.1, 0.2, 0.3], "abs": [None, 0.01, 0.05],
          "max_kaynak": [None, 3, 4, 5], "ilgili": [False, True]}
BASLANGIC = {"k": 6, "rel": 0.1, "abs": None, "max_kaynak": None, "ilgili": False}


def hits_of(row: dict) -> list[Hit]:
    return [Hit(a["chunk_id"], a["madde_id"], a["skor"], a["izler"]) for a in row["adaylar"]]


def run(rows: list[dict], chunks, maddeler, links, ayar: dict, budget: int) -> dict:
    cevapli, cevapsiz = [], []
    for r in rows:
        hits = hits_of(r)[: ayar["k"]]
        if ayar["abs"] is not None:  # en iyi parça her zaman kalır
            hits = [h for i, h in enumerate(hits) if i == 0 or (h.izler.get("rerank") or 0) >= ayar["abs"]]
        ctx = build_context(hits, chunks, maddeler, budget=budget, rel_rerank=ayar["rel"],
                            max_sources=ayar["max_kaynak"], links=links if ayar["ilgili"] else None)
        ids = [c.madde_id for c in ctx]
        gold = set(r["altin_maddeler"])
        rec = {"id": r["id"], "kaynak": len(ids), "token": sum(approx_tokens(c.text) for c in ctx)}
        if gold:
            rec |= {"tam": gold <= set(ids), "herhangi": bool(gold & set(ids)),
                    "gurultu": sum(m not in gold for m in ids)}
            cevapli.append(rec)
        else:
            cevapsiz.append(rec)

    def ort(xs, key):
        return round(statistics.mean(x[key] for x in xs), 3) if xs else None

    return {**ayar, "tam": ort(cevapli, "tam"), "herhangi": ort(cevapli, "herhangi"),
            "kaynak": ort(cevapli, "kaynak"), "gurultu": ort(cevapli, "gurultu"), "token": ort(cevapli, "token"),
            "cevapsiz_kaynak": ort(cevapsiz, "kaynak"),
            "tam_olmayan": [x["id"] for x in cevapli if not x["tam"]]}


def pareto(results: list[dict]) -> list[dict]:
    front = [r for r in results
             if not any(o["tam"] >= r["tam"] and o["gurultu"] <= r["gurultu"]
                        and (o["tam"] > r["tam"] or o["gurultu"] < r["gurultu"]) for o in results)]
    uniq = {(r["tam"], r["gurultu"]): r for r in sorted(front, key=lambda r: (r["kaynak"], r["k"]))[::-1]}
    return sorted(uniq.values(), key=lambda r: r["gurultu"])


def fmt(r: dict) -> str:
    return (f"k={r['k']:<2} rel={r['rel']:<4} abs={r['abs']!s:<4} max={r['max_kaynak']!s:<4} "
            f"ilgili={'+' if r['ilgili'] else '-'} | tam {r['tam']:.3f} · herhangi {r['herhangi']:.3f} · "
            f"kaynak {r['kaynak']:.2f} · gürültü {r['gurultu']:.2f} · token {r['token']:.0f} · "
            f"cevapsız kaynak {r['cevapsiz_kaynak']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump", type=Path)
    ap.add_argument("--out", type=Path, help="varsayılan: <dump>.tarama.json")
    args = ap.parse_args(argv)

    cfg = load_config()
    rows = [json.loads(line) for line in args.dump.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = load_chunks(cfg)
    maddeler = load_maddeler(cfg.data_dir / "processed")
    missing = {a["chunk_id"] for r in rows for a in r["adaylar"]} - set(chunks)
    if missing:
        print(f"Uyarı: dökümdeki {len(missing)} parça yerel chunks.jsonl'de yok (belge sürümü farklı mı?)")
        return 1
    links = load_links(REPO_ROOT / (cfg.section("generation").get("ilgili_maddeler")
                                    or "configs/ilgili_maddeler.yaml"))
    budget = cfg.section("retrieval").get("context_token_budget", 5000)

    keys = list(IZGARA)
    results = [run(rows, chunks, maddeler, links, dict(zip(keys, vals, strict=True)), budget)
               for vals in itertools.product(*IZGARA.values())]
    base = next(r for r in results if all(r[k] == v for k, v in BASLANGIC.items()))
    front = pareto(results)

    print(f"{len(rows)} soru · {len(results)} ayar\n\nBaşlangıç (M3 ayarı):\n  {fmt(base)}\n\nPareto sınırı:")
    for r in front:
        print("  " + fmt(r))
    for n in (3, 4, 5):
        best = max((r for r in results if r["max_kaynak"] == n), key=lambda r: (r["tam"], -r["gurultu"]))
        print(f"\nEn çok {n} kaynakla en iyi:\n  {fmt(best)}\n  tam olmayan: {', '.join(best['tam_olmayan'])}")

    out = args.out or args.dump.with_suffix(".tarama.json")
    out.write_text(json.dumps({"tarih": datetime.now().isoformat(timespec="seconds"), "dump": args.dump.name,
                               "baslangic": base, "pareto": front, "hepsi": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRapor: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
