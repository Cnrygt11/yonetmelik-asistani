"""Parçalama: python -m yonetmelik_asistani.chunking [--oncelik P1]

data/processed/<belge>.txt → data/processed/chunks.jsonl (arama parçaları)
                           → data/processed/maddeler.jsonl (bağlam birimi: maddenin tamamı)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys

from yonetmelik_asistani.chunking.chunker import approx_tokens, chunk_document
from yonetmelik_asistani.chunking.parser import parse_document
from yonetmelik_asistani.config import load_config
from yonetmelik_asistani.ingest.manifest import load_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.chunking")
    parser.add_argument("--oncelik", default="P1", help="virgülle ayrılmış: P1,P2,P3")
    args = parser.parse_args(argv)

    cfg = load_config()
    ch = cfg.section("chunking")
    processed = cfg.data_dir / "processed"
    wanted = set(args.oncelik.split(","))
    belgeler = [b for b in load_manifest() if b.oncelik in wanted and b.durum == "yururlukte"]

    all_chunks, all_maddeler = [], []
    print(f"{'belge':38} {'madde':>5} {'parça':>5} {'ort.tok':>7} {'maks.tok':>8}")
    for b in belgeler:
        src = processed / f"{b.id}.txt"
        if not src.exists():
            print(f"  ! {b.id}: işlenmiş metin yok (önce ingest extract)")
            return 1
        doc = parse_document(b.id, src.read_text(encoding="utf-8"))
        chunks, maddeler = chunk_document(
            b, doc, cfg.corpus_version,
            short_madde_tokens=ch.get("short_madde_tokens", 350), max_tokens=ch.get("max_tokens", 450),
        )
        toks = [approx_tokens(c.text) for c in chunks]
        print(f"{b.id:38} {len(maddeler):>5} {len(chunks):>5} {statistics.mean(toks):>7.0f} {max(toks):>8}")
        all_chunks += chunks
        all_maddeler += maddeler

    ids = [c.chunk_id for c in all_chunks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"HATA: yinelenen parça kimlikleri: {sorted(dupes)[:5]}")
        return 1
    with (processed / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c.to_json(), ensure_ascii=False) + "\n")
    with (processed / "maddeler.jsonl").open("w", encoding="utf-8") as f:
        for m in all_maddeler:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"\n{len(all_chunks)} parça, {len(all_maddeler)} madde → {processed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
