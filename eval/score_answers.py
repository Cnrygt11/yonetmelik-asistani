"""Cevap puanlama ve plan ölçütleri (plan 1 ve 9; Faz 4 M3).

    python eval/score_answers.py eval/reports/cevaplar_gelistirme_v2.jsonl \\
        --puanlar eval/reports/puanlar_gelistirme_v2.jsonl

Puan dosyası (elle, satır başına bir soru):
    {"id": "wa-005", "karar": "dogru" | "kismen" | "yanlis", "not": "..."}
    karar, cevabın altın cevapla örtüşmesidir. Cevapsız sorularda "dogru" = doğru ret veya
    hiçbir şey uydurmadan eksik bilgi + yönlendirme.
    İsteğe bağlı "atif": "dogru" | "yanlis" otomatik atıf kararını geçersiz kılar.

Ölçütler:
  dogru_cevap : cevaplı sorularda "dogru" oranı (hedef %85); "kismen" ayrıca raporlanır
  dogru_atif  : kaynak gösteren cevaplarda, gösterilen maddelerden en az birinin altın madde
                olması (otomatik) ya da puanlayıcının "atif" kararı (hedef %95)
  dogru_ret   : cevapsız sorularda "dogru" oranı (hedef %90)
Puanlanmamış sorular oranlara katılmaz; kaç tane olduğu raporlanır.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_LABEL_RE = re.compile(r"\[K(\d+)\]")
HEDEF = {"dogru_cevap": 0.85, "dogru_atif": 0.95, "dogru_ret": 0.90}


def cited_maddeler(row: dict) -> list[str]:
    by_label = {k["etiket"]: k["madde_id"] for k in row["kaynaklar"]}
    return sorted({by_label[f"K{n}"] for n in _LABEL_RE.findall(row["cevap"]) if f"K{n}" in by_label})


def auto_atif(row: dict) -> bool | None:
    """Kaynak gösteren bir cevapta gösterilen maddelerden biri altın mı; gösterilmemişse None."""
    cited = cited_maddeler(row)
    if not cited or not row["altin_maddeler"]:
        return None
    return bool(set(cited) & set(row["altin_maddeler"]))


def _rate(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def score(rows: list[dict], grades: dict[str, dict]) -> dict:
    out: dict = {"soru": len(rows), "puanlanan": sum(r["id"] in grades for r in rows)}
    groups: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        g = grades.get(r["id"])
        atif = auto_atif(r)
        if g and g.get("atif") in ("dogru", "yanlis"):
            atif = g["atif"] == "dogru"
        for key in ("hepsi", f"kategori:{r['kategori']}", f"kaynak:{r['kaynak']}"):
            b = groups[key]
            if atif is not None:
                b["atif"].append(atif)
            if g is None:
                continue
            if r["altin_maddeler"]:
                b["cevap"].append(g["karar"] == "dogru")
                b["kismen"].append(g["karar"] == "kismen")
            else:
                b["ret"].append(g["karar"] == "dogru")
    for key, b in sorted(groups.items()):
        out[key] = {"dogru_cevap": _rate(b["cevap"]), "kismen": _rate(b["kismen"]), "n_cevapli": len(b["cevap"]),
                    "dogru_atif": _rate(b["atif"]), "n_atif": len(b["atif"]),
                    "dogru_ret": _rate(b["ret"]), "n_cevapsiz": len(b["ret"])}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cevaplar", type=Path)
    ap.add_argument("--puanlar", type=Path)
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in args.cevaplar.read_text(encoding="utf-8").splitlines() if line.strip()]
    grades = {}
    if args.puanlar and args.puanlar.exists():
        grades = {g["id"]: g for g in map(json.loads, args.puanlar.read_text(encoding="utf-8").splitlines()) if g}
    res = score(rows, grades)
    h = res["hepsi"]
    print(f"{res['soru']} cevap · {res['puanlanan']} puanlandı")
    for k, label in (("dogru_cevap", "Doğru cevap"), ("dogru_atif", "Doğru atıf"), ("dogru_ret", "Doğru ret")):
        v = h[k]
        mark = "" if v is None else ("✓" if v >= HEDEF[k] else "✗")
        print(f"  {label:12} {'-' if v is None else f'{v:.1%}':>7}  (hedef {HEDEF[k]:.0%}) {mark}")
    if h["kismen"] is not None:
        print(f"  {'Kısmen':12} {h['kismen']:.1%}")
    print("\nKategoriye göre doğru cevap:")
    for key, v in res.items():
        if key.startswith("kategori:") and v["n_cevapli"]:
            print(f"  {key[9:]:16} {v['dogru_cevap']:.0%}  (n={v['n_cevapli']}, kısmen {v['kismen']:.0%})")
    out = args.cevaplar.with_suffix(".puan.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRapor: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
