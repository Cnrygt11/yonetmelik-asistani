"""Derlem komutları (Faz 1).

    python -m yonetmelik_asistani.ingest index      # KAYSİS listesini kaydet, değişenleri göster
    python -m yonetmelik_asistani.ingest download   # manifest'teki belgeleri indir, kilidi güncelle
    python -m yonetmelik_asistani.ingest extract    # metni çıkar ve güncelliği doğrula

`download` ve `extract` varsayılan olarak P1 belgelerle çalışır; `--oncelik P1,P2` veya
`--id <belge>` ile daraltılıp genişletilebilir. `extract`, bir güncellik sorunu bulursa 1 ile çıkar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

from yonetmelik_asistani.config import load_config
from yonetmelik_asistani.ingest import kaysis
from yonetmelik_asistani.ingest.extract import MADDE_RE, extract_pdf
from yonetmelik_asistani.ingest.manifest import Belge, Kaynak, load_lock, load_manifest, save_lock
from yonetmelik_asistani.ingest.verify import cross_check, verify


def _select(belgeler: list[Belge], oncelik: str, only: str | None) -> list[Belge]:
    if only:
        sel = [b for b in belgeler if b.id == only]
        if not sel:
            sys.exit(f"Manifest'te '{only}' yok")
        return sel
    wanted = set(oncelik.split(","))
    return [b for b in belgeler if b.oncelik in wanted and b.durum == "yururlukte"]


def cmd_index(raw_dir: Path) -> int:
    with kaysis.make_client() as client:
        docs = kaysis.fetch_index(client)
    path = raw_dir / "kaysis_index.json"
    old = {d["goster_id"]: d for d in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
    new = {d.goster_id: {"goster_id": d.goster_id, "baslik": d.baslik, "bolum": d.bolum} for d in docs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(new.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    added = [new[i] for i in new.keys() - old.keys()]
    removed = [old[i] for i in old.keys() - new.keys()]
    print(f"KAYSİS: {len(new)} belge → {path}")
    if old:
        for d in added:
            print(f"  + {d['goster_id']} [{d['bolum']}] {d['baslik']}")
        for d in removed:
            print(f"  - {d['goster_id']} [{d['bolum']}] {d['baslik']}")
        if not added and not removed:
            print("  Önceki listeye göre değişiklik yok.")
    return 0


def _fetch(src: Kaynak, kaysis_client: httpx.Client, web_client: httpx.Client) -> tuple[bytes, str, str, str]:
    """(içerik, içerik türü, kaynak etiketi, adres) döndürür."""
    if src.tur == "kaysis" and src.id is not None:
        content, ctype = kaysis.fetch_document(kaysis_client, src.id)
        return content, ctype, f"kaysis:{src.id}", f"{kaysis.BASE_URL}/Home/Goster/{src.id}"
    if src.tur == "url" and src.url:
        resp = web_client.get(src.url)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "").split(";")[0].strip(), "url", src.url
    raise ValueError(f"desteklenmeyen kaynak: {src}")


def cmd_download(belgeler: list[Belge], raw_dir: Path) -> int:
    lock = load_lock()
    web = httpx.Client(follow_redirects=True, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
    with kaysis.make_client() as client, web:
        for b in belgeler:
            if not b.kaynaklar:
                print(f"  ! {b.id}: kaynak yok, atlandı")
                continue
            content, ctype, label, url = _fetch(b.kaynaklar[0], client, web)
            ext = ".pdf" if ctype == "application/pdf" else ".bin"
            stem = label.replace(":", "_")
            dest = raw_dir / b.id / f"{stem}{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            sha = hashlib.sha256(content).hexdigest()
            prev = lock.get(b.id, {}).get("sha256")
            status = "yeni" if prev is None else ("DEĞİŞTİ" if prev != sha else "aynı")
            lock[b.id] = {
                "kaynak": label,
                "url": url,
                "dosya": dest.relative_to(raw_dir).as_posix(),
                "icerik_turu": ctype,
                "bayt": len(content),
                "sha256": sha,
                "indirme": datetime.now().isoformat(timespec="seconds"),
            }
            print(f"  {status:7} {b.id}  ({len(content) // 1024} KB)")
    save_lock(lock)
    return 0


def cmd_extract(belgeler: list[Belge], raw_dir: Path, out_dir: Path) -> int:
    lock = load_lock()
    problems = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for b in belgeler:
        entry = lock.get(b.id)
        if not entry:
            print(f"  ! {b.id}: indirilmemiş (önce download)")
            problems += 1
            continue
        path = raw_dir / entry["dosya"]
        if not path.exists():
            print(f"  ! {b.id}: dosya yok: {path}")
            problems += 1
            continue
        # Elle kopyalanan dosyalar (ör. Colab'da Drive'a yüklenen) kilitteki sürümle aynı olmalı
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            print(f"  ! {b.id}: dosya kilitteki sha256 ile uyuşmuyor (önce download)")
            problems += 1
            continue
        ex = extract_pdf(path)
        (out_dir / f"{b.id}.txt").write_text(ex.text + "\n", encoding="utf-8")
        issues = verify(b, ex)
        meta = {
            "id": b.id, "kaynak": entry["kaynak"], "sha256": entry["sha256"], "sayfa": ex.pages,
            "karakter": len(ex.text), "madde": sum(1 for line in ex.text.split("\n") if MADDE_RE.match(line)),
            "bicim": ex.bicim, "tablo": ex.tables, "resimli_sayfalar": ex.image_pages,
            "pdf_yayim": str(ex.yayim) if ex.yayim else None,
            "pdf_degisiklikler": [str(r) for r in ex.degisiklikler],
            "notlar_rg": {str(k): v for k, v in sorted(ex.annotation_counts.items(), key=lambda kv: kv[0].tarih)},
            "sorunlar": issues,
        }
        (out_dir / f"{b.id}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        mark = "OK " if not issues else "SORUN"
        print(f"  {mark} {b.id}: {ex.bicim}, {ex.pages} sayfa, {meta['madde']} madde, "
              f"{ex.tables} tablo, {len(ex.degisiklikler)} değişiklik")
        for issue in issues:
            print(f"        - {issue}")
        problems += bool(issues)
    return 1 if problems else 0


def cmd_crosscheck(belgeler: list[Belge], raw_dir: Path, out_dir: Path) -> int:
    """Birincil metni, manifest'teki ikinci kaynakla madde madde karşılaştırır."""
    problems = 0
    web = httpx.Client(follow_redirects=True, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
    with kaysis.make_client() as client, web:
        for b in belgeler:
            if len(b.kaynaklar) < 2:
                continue
            primary = out_dir / f"{b.id}.txt"
            if not primary.exists():
                print(f"  ! {b.id}: önce extract")
                problems += 1
                continue
            content, _, label, _ = _fetch(b.kaynaklar[1], client, web)
            dest = raw_dir / b.id / "capraz.pdf"
            dest.write_bytes(content)
            cc = cross_check(primary.read_text(encoding="utf-8"), extract_pdf(dest).text,
                             b.capraz_bilinen_farklar)
            mark = "OK " if not cc.issues else "SORUN"
            known = f", {len(cc.bilinen)} bilinen fark" if cc.bilinen else ""
            print(f"  {mark} {b.id} ↔ {label}: {cc.ayni}/{cc.ortak} madde aynı{known}")
            for issue in cc.issues:
                print(f"        - {issue}")
            problems += bool(cc.issues)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yonetmelik_asistani.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="KAYSİS belge listesini indir ve değişiklikleri göster")
    for name in ("download", "extract", "crosscheck"):
        p = sub.add_parser(name)
        p.add_argument("--oncelik", default="P1", help="virgülle ayrılmış: P1,P2,P3")
        p.add_argument("--id", dest="only", help="tek bir belge kimliği")
    args = parser.parse_args(argv)

    cfg = load_config()
    raw_dir, out_dir = cfg.data_dir / "raw", cfg.data_dir / "processed"
    if args.cmd == "index":
        return cmd_index(raw_dir)
    belgeler = _select(load_manifest(), args.oncelik, args.only)
    if args.cmd == "download":
        return cmd_download(belgeler, raw_dir)
    if args.cmd == "crosscheck":
        return cmd_crosscheck(belgeler, raw_dir, out_dir)
    return cmd_extract(belgeler, raw_dir, out_dir)
