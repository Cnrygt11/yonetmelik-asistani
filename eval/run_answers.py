"""Altın set üzerinde cevap üretimi ve otomatik ön kontroller (Faz 4, M3).

    python eval/run_answers.py --out yol.jsonl            # geliştirme bölümü (134 soru)
    python eval/run_answers.py --out yol.jsonl --limit 10 # deneme
    python eval/run_answers.py --out yol.jsonl            # yarıda kaldıysa: aynı komut kaldığı yerden sürer
    python eval/run_answers.py --out yol.jsonl --istem v3 --ids-file eval/alt_set_40.txt --think

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
import hashlib
import json
import statistics
import sys
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_gold

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.llm_client import LLMClient
from yonetmelik_asistani.generation.pipeline import (
    answer,
    load_links,
    load_maddeler,
    load_repealed,
    numbers_covered,
)
from yonetmelik_asistani.generation.prompts import (
    PROMPT_VERSION,
    PROMPT_VERSIONS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V3,
)
from yonetmelik_asistani.retrieval.service import load_retriever
from yonetmelik_asistani.smoke import gpu_report


def settings_digest(cfg, ayar: dict) -> str:
    """Cevapları etkileyen her şeyin özeti: sözlük, bağlantılı maddeler, istem metni, arama ve üretim
    ayarları, belge sürümü. Yarıda kalan dosyaya yalnızca özet aynıysa devam edilir."""
    h = hashlib.sha256()
    paths = cfg.section("paths")
    for rel in (paths.get("glossary", "data/glossary.yaml"), cfg.section("generation").get("ilgili_maddeler")):
        if rel and (REPO_ROOT / rel).exists():
            h.update((REPO_ROOT / rel).read_bytes())
    h.update((SYSTEM_PROMPT_V3 if ayar["istem"] == "v3" else SYSTEM_PROMPT).encode())
    h.update(json.dumps({**ayar, "model": cfg.llm.model, "corpus": cfg.corpus_version,
                         **{k: cfg.section(k) for k in ("retrieval", "reranker", "embedding", "generation")}},
                        sort_keys=True, ensure_ascii=False, default=str).encode())
    return h.hexdigest()[:12]


def summarize(rows: list[dict]) -> dict:
    cevapli = [r for r in rows if r["altin_maddeler"]]
    tam = [r for r in cevapli if "altin_tamami_baglamda" in r]
    cevapsiz = [r for r in rows if not r["altin_maddeler"]]
    sayi = [r["sayi_kapsami"] for r in cevapli if r["sayi_kapsami"] is not None]

    def oran(xs, f):
        return round(sum(map(f, xs)) / len(xs), 3) if xs else None

    return {
        "soru": len(rows), "cevapli": len(cevapli), "cevapsiz": len(cevapsiz),
        "altin_baglamda": oran(cevapli, lambda r: r["altin_baglamda"]),
        "altin_tamami_baglamda": oran(tam, lambda r: r["altin_tamami_baglamda"]),
        "kaynak_sayisi_ort": round(statistics.mean(len(r["kaynaklar"]) for r in rows), 2) if rows else None,
        "json_hatasi": sum(r.get("json_hatasi", False) for r in rows),
        "gecersiz_alinti": sum(not q["gecerli"] for r in rows for q in r.get("alintilar") or []),
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
    ap.add_argument("--ids-file", type=Path, help="satır başına bir soru kimliği (ör. eval/alt_set_40.txt)")
    ap.add_argument("--istem", choices=PROMPT_VERSIONS, default=PROMPT_VERSION)
    ap.add_argument("--think", action="store_true", help="düşünme kipi (Qwen); üretim sınırı ve bağlam büyütülür")
    ap.add_argument("--max-tokens", type=int, help="üretim sınırı (varsayılan: v2 yapılandırma, v3 1000, think 3000)")
    ap.add_argument("--max-kaynak", type=int, help="bağlamdaki en çok kaynak (yapılandırmayı ezer)")
    ap.add_argument("--ilgili", choices=["acik", "kapali"], default="acik", help="bağlantılı maddeler")
    args = ap.parse_args(argv)

    cfg = load_config()
    gold = load_gold()
    subset = [g for g in gold if args.split == "hepsi" or g["bolum"] == args.split]
    if args.ids:
        wanted = set(args.ids.split(","))
        subset = [g for g in gold if g["id"] in wanted]
    if args.ids_file:
        lines = args.ids_file.read_text(encoding="utf-8").splitlines()
        wanted = {x.strip() for x in lines if x.strip() and not x.startswith("#")}
        subset = [g for g in gold if g["id"] in wanted]
    if args.limit:
        subset = subset[: args.limit]

    done = {}
    if args.out.exists():
        done = {r["id"]: r for r in map(json.loads, args.out.read_text(encoding="utf-8").splitlines()) if r}
    todo = [g for g in subset if g["id"] not in done]
    print(f"{len(subset)} soru · {len(done)} hazır · {len(todo)} üretilecek · istem {args.istem}"
          + (" · düşünme açık" if args.think else ""))

    budget = cfg.section("retrieval").get("context_token_budget", 5000)
    gen = cfg.section("generation")
    rel = gen.get("rel_rerank", 0.1)
    max_sources = args.max_kaynak or gen.get("max_sources")
    links = (load_links(REPO_ROOT / gen["ilgili_maddeler"])
             if args.ilgili == "acik" and gen.get("ilgili_maddeler") else {})
    max_tokens = args.max_tokens or (3000 if args.think else 1000 if args.istem == "v3" else None)
    llm_cfg = cfg.llm
    if args.think:  # düşünce token'ları da bağlam penceresine sığmalı
        llm_cfg = replace(llm_cfg, num_ctx=max(llm_cfg.num_ctx, 12288))
    ayar = {"istem": args.istem, "think": args.think, "max_tokens": max_tokens, "num_ctx": llm_cfg.num_ctx,
            "max_kaynak": max_sources, "ilgili": bool(links), "rel_rerank": rel, "butce": budget}
    ayar["ozet"] = settings_digest(replace(cfg, llm=llm_cfg), ayar)
    if done:  # başka ayarla üretilmiş dosyaya ekleme yapılmaz (eski cevaplar yeni ölçüm sanılır)
        old = (next(iter(done.values())).get("ayar") or {}).get("ozet")  # eski biçimde yok: yine reddedilir
        if old != ayar["ozet"]:
            print(f"HATA: {args.out} başka ayarlarla üretilmiş (özet {old} ≠ {ayar['ozet']}): sözlük, bağlantılı "
                  "maddeler, istem, model ya da arama ayarı değişmiş. Yeni bir --out verin.")
            return 2
    retriever = load_retriever(cfg)
    maddeler = load_maddeler(cfg.data_dir / "processed")
    repealed = load_repealed(REPO_ROOT / cfg.section("paths").get("manifest", "configs/corpus_manifest.yaml"))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with LLMClient(llm_cfg) as llm, args.out.open("a", encoding="utf-8") as fh:
        if todo:
            warm = llm.chat([{"role": "user", "content": "Merhaba"}], think=False, max_tokens=20)
            print(f"Isınma: {warm.wall_s:.1f} sn · GPU: {gpu_report()}")
        for i, g in enumerate(todo, 1):
            a = answer(g["soru"], retriever, llm, maddeler, profile=g.get("profil"), budget=budget,
                       rel_rerank=rel, max_sources=max_sources, links=links, repealed=repealed,
                       istem=args.istem, think=args.think, max_tokens=max_tokens)
            baglam = [k["madde_id"] for k in a.kaynaklar]
            row = {"id": g["id"], "kategori": g["kategori"], "kaynak": g.get("kaynak", "ilk"),
                   "altin_maddeler": g["altin_maddeler"], "altin_cevap": g["altin_cevap"],
                   "altin_baglamda": bool(set(g["altin_maddeler"]) & set(baglam)),
                   "altin_tamami_baglamda": bool(g["altin_maddeler"]) and set(g["altin_maddeler"]) <= set(baglam),
                   "sayi_kapsami": numbers_covered(g.get("alinti"), a.cevap),
                   "sozluk": retriever.last_expansion, "ayar": ayar,
                   **asdict(a)}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            done[g["id"]] = row
            flag = "RET" if a.ret else "cevap"
            if a.json_hatasi:
                flag = "JSON!"
            print(f"[{i}/{len(todo)}] {g['id']:7} {flag:5} {a.sure_s:5.1f} sn · altın bağlamda: "
                  f"{row['altin_baglamda']}" + (" · KARMA" if a.karma else ""), flush=True)

    rows = [done[g["id"]] for g in subset if g["id"] in done]
    ozet = {"tarih": datetime.now().isoformat(timespec="seconds"), "model": cfg.llm.model, **ayar,
            "corpus_version": cfg.corpus_version, "split": args.split, **summarize(rows)}
    args.out.with_suffix(".ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
