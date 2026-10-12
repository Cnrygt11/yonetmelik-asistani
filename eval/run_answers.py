"""Altın set üzerinde cevap üretimi ve otomatik ön kontroller (Faz 4, M3).

    python eval/run_answers.py --out yol.jsonl            # geliştirme bölümü (134 soru)
    python eval/run_answers.py --out yol.jsonl --limit 10 # deneme
    python eval/run_answers.py --out yol.jsonl            # yarıda kaldıysa: aynı komut kaldığı yerden sürer

Her cevap üretildiği anda çıktı dosyasına bir satır olarak yazılır (Colab oturumu düşerse kayıp
olmaz). Sorunun `profil` alanı (fakülte) aramaya ve isteme verilir.

Otomatik ön kontroller (doğruluk puanı değildir; puanlama ayrıca yapılır):
  altin_baglamda : altın maddelerden en az biri modelin önündeki bağlamda mı
  sayi_kapsami   : altın alıntıdaki sayıların cevapta geçme oranı
  ret / karma    : ret cümlesi; ret ile kaynak etiketi birlikte (istem kuralı 4'e aykırı)
Sonda özet basılır ve `<out>.ozet.json` yazılır.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_gold

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.llm_client import LLMClient
from yonetmelik_asistani.generation.pipeline import (
    answer,
    load_maddeler,
    load_repealed,
    numbers_covered,
)
from yonetmelik_asistani.generation.prompts import PROMPT_VERSION
from yonetmelik_asistani.retrieval.service import load_retriever
from yonetmelik_asistani.smoke import gpu_report


def summarize(rows: list[dict]) -> dict:
    cevapli = [r for r in rows if r["altin_maddeler"]]
    cevapsiz = [r for r in rows if not r["altin_maddeler"]]
    sayi = [r["sayi_kapsami"] for r in cevapli if r["sayi_kapsami"] is not None]

    def oran(xs, f):
        return round(sum(map(f, xs)) / len(xs), 3) if xs else None

    return {
        "soru": len(rows), "cevapli": len(cevapli), "cevapsiz": len(cevapsiz),
        "altin_baglamda": oran(cevapli, lambda r: r["altin_baglamda"]),
        "cevapliya_ret": oran(cevapli, lambda r: r["ret"] and not r["karma"]),
        "cevapsiza_dogru_ret": oran(cevapsiz, lambda r: r["ret"] and not r["karma"]),
        "karma": sum(r["karma"] for r in rows),
        "etiket_hatasi": sum(bool(r["etiket_hatalari"]) for r in rows),
        "etiketsiz": sum(r["etiketsiz"] for r in rows),
        "sayi_kapsami_ort": round(statistics.mean(sayi), 3) if sayi else None,
        "sure_medyan_s": statistics.median(r["sure_s"] for r in rows) if rows else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", choices=["gelistirme", "test", "hepsi"], default="gelistirme")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="virgülle ayrılmış soru kimlikleri")
    args = ap.parse_args(argv)

    cfg = load_config()
    gold = load_gold()
    subset = [g for g in gold if args.split == "hepsi" or g["bolum"] == args.split]
    if args.ids:
        wanted = set(args.ids.split(","))
        subset = [g for g in gold if g["id"] in wanted]
    if args.limit:
        subset = subset[: args.limit]

    done = {}
    if args.out.exists():
        done = {r["id"]: r for r in map(json.loads, args.out.read_text(encoding="utf-8").splitlines()) if r}
    todo = [g for g in subset if g["id"] not in done]
    print(f"{len(subset)} soru · {len(done)} hazır · {len(todo)} üretilecek · istem {PROMPT_VERSION}")

    retriever = load_retriever(cfg)
    maddeler = load_maddeler(cfg.data_dir / "processed")
    repealed = load_repealed(REPO_ROOT / cfg.section("paths").get("manifest", "configs/corpus_manifest.yaml"))
    budget = cfg.section("retrieval").get("context_token_budget", 5000)
    rel = cfg.section("generation").get("rel_rerank", 0.1)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with LLMClient(cfg.llm) as llm, args.out.open("a", encoding="utf-8") as fh:
        if todo:
            warm = llm.chat([{"role": "user", "content": "Merhaba"}])
            print(f"Isınma: {warm.wall_s:.1f} sn · GPU: {gpu_report()}")
        for i, g in enumerate(todo, 1):
            a = answer(g["soru"], retriever, llm, maddeler, profile=g.get("profil"), budget=budget,
                       rel_rerank=rel, repealed=repealed)
            baglam = [k["madde_id"] for k in a.kaynaklar]
            row = {"id": g["id"], "kategori": g["kategori"], "kaynak": g.get("kaynak", "ilk"),
                   "altin_maddeler": g["altin_maddeler"], "altin_cevap": g["altin_cevap"],
                   "altin_baglamda": bool(set(g["altin_maddeler"]) & set(baglam)),
                   "sayi_kapsami": numbers_covered(g.get("alinti"), a.cevap),
                   "sozluk": retriever.last_expansion, "istem": PROMPT_VERSION,
                   **asdict(a)}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            done[g["id"]] = row
            flag = "RET" if a.ret else "cevap"
            print(f"[{i}/{len(todo)}] {g['id']:7} {flag:5} {a.sure_s:5.1f} sn · altın bağlamda: "
                  f"{row['altin_baglamda']}" + (" · KARMA" if a.karma else ""), flush=True)

    rows = [done[g["id"]] for g in subset if g["id"] in done]
    ozet = {"tarih": datetime.now().isoformat(timespec="seconds"), "model": cfg.llm.model, "istem": PROMPT_VERSION,
            "corpus_version": cfg.corpus_version, "split": args.split, **summarize(rows)}
    args.out.with_suffix(".ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
