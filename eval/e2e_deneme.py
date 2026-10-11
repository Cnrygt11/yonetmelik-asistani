"""Uçtan uca deneme: aynı T4'te Ollama + BGE-M3 + reranker, kaynak gösteren cevap (Faz 4 öncesi).

    python eval/e2e_deneme.py [--report yol.json]

Amaç ölçmek değil, bütünleşme sorunlarını erken görmek: bellek, süre, kaynak etiketleri, ret.
Sorular bilerek seçildi; her birinin neyi sınadığı yanında yazıyor.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.llm_client import LLMClient
from yonetmelik_asistani.generation.pipeline import answer, load_maddeler
from yonetmelik_asistani.retrieval.service import load_retriever
from yonetmelik_asistani.smoke import gpu_report

SORULAR = [
    ("Kaydımı dondurmak istiyorum, ne zamana kadar başvurmalıyım?",
     "iki ayrı süre (md. 19/1 ve 19/2) birlikte verilmeli"),
    ("Tek ders sınavına kimler girebiliyor?", "öğrenci dili: yönetmelikte adı 'ek sınav' (md. 31)"),
    ("Harcımı ödemezsem okuldan atılır mıyım?", "18.08.2024 değişikliği: 4 yıl üst üste ödememe (md. 39)"),
    ("Azami süremi doldurdum ve son sınıftayım, kaç ek sınav hakkım var?",
     "2547 md. 44, 30.07.2026'da 7592 ile değişti"),
    ("Okuldan kaydım silinmişti, öğrenim affından yararlanabilir miyim?",
     "2547 geçici md. 85 derlemde yok: ret beklenir"),
    ("Yurt ücretleri ne kadar?", "derlem dışı: ret beklenir"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path)
    ap.add_argument("--duzey", default="lisans")
    args = ap.parse_args(argv)

    cfg = load_config()
    retriever = load_retriever(cfg)
    maddeler = load_maddeler(cfg.data_dir / "processed")
    budget = cfg.section("retrieval").get("context_token_budget", 5000)
    results = []
    with LLMClient(cfg.llm) as llm:
        warm = llm.chat([{"role": "user", "content": "Merhaba"}])
        print(f"Isınma: {warm.wall_s:.1f} sn · GPU: {gpu_report()}\n")
        for soru, beklenti in SORULAR:
            a = answer(soru, retriever, llm, maddeler, profile={"duzey": args.duzey}, budget=budget)
            results.append({**asdict(a), "beklenti": beklenti})
            durum = "RET" if a.ret else ("ETİKETSİZ" if a.etiketsiz else "cevap")
            print(f"■ {soru}\n  beklenti: {beklenti}")
            print(f"  {durum} · {a.sure_s} sn · ilk rerank {a.ilk_rerank} · "
                  f"bağlam {sum(k['token'] for k in a.kaynaklar)} tok / {len(a.kaynaklar)} kaynak"
                  + (f" · GEÇERSİZ ETİKET {a.etiket_hatalari}" if a.etiket_hatalari else ""))
            for k in a.kaynaklar:
                print(f"    [{k['etiket']}] {k['baslik'][:150]}")
            print("  " + a.cevap.replace("\n", "\n  ") + "\n")
    gpu = gpu_report()
    print(f"GPU (son): {gpu}")

    report = args.report or REPO_ROOT / "eval" / "reports" / f"e2e_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"tarih": datetime.now().isoformat(timespec="seconds"), "model": cfg.llm.model,
                                  "corpus_version": cfg.corpus_version, "gpu": gpu, "isinma_s": round(warm.wall_s, 1),
                                  "sonuclar": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Rapor: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
