"""Kör puanlama seti hazırlar (puanlayıcı kalibrasyonu; FAZ_4.md "Rota düzeltmesi", karar 2).

    python eval/puanlama_hazirla.py                      # set1: 27B sabit 40 + M3'ten 20 gerçek soru
    python eval/puanlama_hazirla.py --cikti eval/puanlama/set1.html

Proje sahibi ve asistan aynı cevapları birbirinden bağımsız, aynı evet/hayır sorularıyla puanlar;
karşılaştırma eval/puanlama_karsilastir.py ile yapılır. Sayfa kurulumsuz tek HTML dosyasıdır
(eval/puanlama/sablon.html): cevap, modelin gördüğü madde metinleri ve sorular; hangi modelin
cevap verdiği gösterilmez, altın cevap puan kaydedildikten sonra açılır. Puanlar tarayıcıda
saklanır ve JSONL olarak dışa aktarılır.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_gold

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.pipeline import load_maddeler

REPORTS = REPO_ROOT / "eval" / "reports"
SABLON = REPO_ROOT / "eval" / "puanlama" / "sablon.html"


def item(row: dict, model: str, gold: dict, maddeler: dict) -> dict:
    import re

    cited = {f"K{n}" for n in re.findall(r"\[K(\d+)\]", row["cevap"])}
    kaynaklar = []
    for k in row["kaynaklar"]:
        m = maddeler.get(k["madde_id"], {})
        kaynaklar.append({"etiket": k["etiket"], "baslik": m.get("path", k["baslik"]), "metin": m.get("text", ""),
                          "gosterilen": k["etiket"] in cited})
    g = gold[row["id"]]
    return {"soru_id": row["id"], "model": model, "soru": g["soru"], "profil": g.get("profil") or {},
            "cevap": row["cevap"], "ret": row["ret"], "kaynaklar": kaynaklar,
            "altin_cevap": g["altin_cevap"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cikti", type=Path, default=REPO_ROOT / "eval" / "puanlama" / "set1.html")
    ap.add_argument("--tohum", type=int, default=20261013)
    args = ap.parse_args(argv)

    cfg = load_config()
    maddeler = load_maddeler(cfg.data_dir / "processed")
    gold = {g["id"]: g for g in load_gold()}
    rng = random.Random(args.tohum)

    def rows(name):
        return [json.loads(line) for line in (REPORTS / name).read_text(encoding="utf-8").splitlines() if line]

    alt40 = rows("cevaplar_alt40_v3_27b.jsonl")
    ids40 = {r["id"] for r in alt40}
    m3_real = [r for r in rows("cevaplar_gelistirme_v2.jsonl") if r["kaynak"] == "whatsapp" and r["id"] not in ids40]
    items = ([item(r, "27b-v3", gold, maddeler) for r in alt40]
             + [item(r, "9b-v2", gold, maddeler) for r in rng.sample(m3_real, 20)])
    rng.shuffle(items)
    for i, it in enumerate(items, 1):
        it["oge"] = f"p{i:02d}"

    set_adi = args.cikti.stem
    veri = json.dumps({"set": set_adi, "ogeler": items}, ensure_ascii=False).replace("</", "<\\/")
    html = SABLON.read_text(encoding="utf-8").replace("/*VERI*/null", veri)
    args.cikti.parent.mkdir(parents=True, exist_ok=True)
    args.cikti.write_text(html, encoding="utf-8")
    print(f"{len(items)} öğe ({sum(it['model'] == '27b-v3' for it in items)} 27B, "
          f"{sum(it['model'] == '9b-v2' for it in items)} 9B; {sum(it['ret'] for it in items)} ret) → {args.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
