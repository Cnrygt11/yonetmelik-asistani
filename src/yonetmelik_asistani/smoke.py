"""Faz 0 sağlık kontrolü: GPU, LLM sunucusu, Türkçe üretim ve ret davranışı.

Kullanım:
    python -m yonetmelik_asistani.smoke [--model qwen3.5:9b] [--report yol.json]

Henüz derlem olmadığı için sorular olgu doğruluğunu değil şunları ölçer:
  * model sunucuda var mı, düşünme modu gerçekten kapalı mı,
  * Türkçe akıcılık ve gecikme (NFR-03 için ilk ölçüm),
  * boş bağlamda modelin ret cümlesini kullanıp kullanmadığı (FR-03'ün ilk işareti).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from yonetmelik_asistani.config import REPO_ROOT, load_config
from yonetmelik_asistani.generation.llm_client import LLMClient, LLMError
from yonetmelik_asistani.generation.prompts import RET_CUMLESI, build_messages
from yonetmelik_asistani.ingest.normalize import turkish_lower

FLUENCY_QUESTIONS = [
    "Bir üniversite öğrencisine kayıt dondurmanın ne anlama geldiğini iki cümleyle açıkla.",
    "Bütünleme sınavı ile mazeret sınavı arasındaki farkı genel olarak, kısaca anlat.",
    "Çift anadal ve yan dal programlarının amacını üç cümleyle karşılaştır.",
    "Yatay geçiş düşünen bir öğrencinin akademik danışmanına sorabileceği üç soruyu madde madde yaz.",
]
ABSTAIN_QUESTION = "Yaz öğretiminde en fazla kaç AKTS ders alabilirim?"


def gpu_report() -> str:
    if not shutil.which("nvidia-smi"):
        return "nvidia-smi bulunamadı (GPU yok veya sürücü yüklü değil)"
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip() or out.stderr.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="Yapılandırmadaki modeli geçersiz kılar")
    parser.add_argument("--report", type=Path, help="JSON raporunun yolu")
    args = parser.parse_args(argv)

    cfg = load_config()
    model = args.model or cfg.llm.model
    print(f"GPU      : {gpu_report()}")
    print(f"Sunucu   : {cfg.llm.backend} @ {cfg.llm.base_url}")
    print(f"Model    : {model} (num_ctx={cfg.llm.num_ctx}, think={cfg.llm.think})\n")

    results: list[dict] = []
    failures: list[str] = []
    with LLMClient(cfg.llm) as client:
        try:
            available = client.list_models()
        except LLMError as e:
            print(f"HATA: {e}")
            return 2
        if model not in available:
            print(f"HATA: '{model}' sunucuda yok. Önce: ollama pull {model}")
            print(f"Mevcut modeller: {', '.join(available) or '(yok)'}")
            return 2

        # Modeli GPU'ya yükler; bu süre soru gecikmesine karıştırılmaz.
        warm = client.chat([{"role": "user", "content": "Merhaba"}], model=model)
        print(f"[Isınma] {warm.wall_s:5.1f} sn (model yükleme dahil)\n")

        for i, q in enumerate(FLUENCY_QUESTIONS, 1):
            r = client.chat([{"role": "user", "content": q}], model=model)
            leaked = "<think>" in r.text
            if leaked:
                failures.append(f"S{i}: çıktıda <think> bloğu var; düşünme modu kapanmamış")
            if not r.text.strip():
                failures.append(f"S{i}: boş cevap")
            results.append({"tur": "akicilik", "soru": q, **asdict(r)})
            tps = f"{r.gen_tokens_per_s:.1f} token/sn" if r.gen_tokens_per_s else "-"
            print(f"[S{i}] {r.wall_s:5.1f} sn · {tps}")
            print(f"     {r.text.strip()[:300]}\n")

        messages = build_messages(ABSTAIN_QUESTION, context=[], duzey="lisans", birim="tum")
        r = client.chat(messages, model=model)
        abstained = turkish_lower("bulamadım") in turkish_lower(r.text)
        if not abstained:
            failures.append("S5: boş bağlamda ret cümlesi kullanılmadı")
        results.append({"tur": "ret", "soru": ABSTAIN_QUESTION, "ret_dogru": abstained, **asdict(r)})
        print(f"[S5] {r.wall_s:5.1f} sn · ret {'DOĞRU' if abstained else 'YANLIŞ'}")
        print(f"     {r.text.strip()[:300]}")
        print(f"     (beklenen: \"{RET_CUMLESI}\")\n")

    report = args.report or (
        REPO_ROOT / "eval" / "reports" / f"smoke_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {"tarih": datetime.now().isoformat(timespec="seconds"), "gpu": gpu_report(),
             "model": model, "llm_ayarlari": asdict(cfg.llm),
             "isinma_s": round(warm.wall_s, 2), "sonuclar": results,
             "hatalar": failures},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Rapor: {report}")
    if failures:
        print("BAŞARISIZ:\n  - " + "\n  - ".join(failures))
        return 1
    print("Tüm kontroller geçti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
