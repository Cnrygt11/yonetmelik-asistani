"""Derlem manifesti (configs/corpus_manifest.yaml) ve kilit dosyası (configs/corpus_lock.json).

Manifest elle düzenlenir: hangi belge, hangi kaynaktan, hangi öncelikle.
Kilit dosyası betiklerce yazılır: indirilen dosyanın özeti, boyutu ve tarihi. Yorumlu YAML'ı
programla yeniden yazmamak için bu iki bilgi ayrı tutulur (uv.lock gibi).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from yonetmelik_asistani.config import CONFIG_DIR
from yonetmelik_asistani.ingest.extract import RGRef

MANIFEST_PATH = CONFIG_DIR / "corpus_manifest.yaml"
LOCK_PATH = CONFIG_DIR / "corpus_lock.json"
DURUMLAR = ("yururlukte", "kaldirildi", "arsiv", "inceleme")


@dataclass(frozen=True)
class Kaynak:
    tur: str  # kaysis | url
    id: int | None = None
    url: str | None = None


@dataclass(frozen=True)
class Teyit:
    """İlk yayım nüshası olan bir yönetmeliğin değişmediğinin başka kaynaklarla teyidi."""

    tarih: date
    kaynaklar: list[str]


@dataclass(frozen=True)
class Belge:
    id: str
    baslik: str
    tur: str
    hiyerarsi: int
    oncelik: str
    durum: str
    birim: list[str] = field(default_factory=lambda: ["tum"])
    duzey: list[str] = field(default_factory=list)
    yayim: RGRef | None = None
    degisiklikler: list[RGRef] = field(default_factory=list)
    kaynaklar: list[Kaynak] = field(default_factory=list)
    degisiklik_teyidi: Teyit | None = None
    maddeler: list[str] | None = None  # yalnızca bu madde anahtarları: "44", geçici "G85", ek "E32"
    capraz_bilinen_farklar: dict[str, str] = field(default_factory=dict)  # madde → açıklama
    zorunlu_ifadeler: list[str] = field(default_factory=list)  # metinde geçmesi gereken (ör. AYM notu)
    notlar: str | None = None


def _date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _rg(raw: dict[str, Any] | None) -> RGRef | None:
    if not raw or not raw.get("tarih") or not raw.get("rg_sayi"):
        return None
    return RGRef(_date(raw["tarih"]), int(raw["rg_sayi"]))


def _belge(raw: dict[str, Any]) -> Belge:
    if raw.get("durum") not in DURUMLAR:
        raise ValueError(f"{raw.get('id')}: durum {DURUMLAR} içinden biri olmalı")
    return Belge(
        id=raw["id"],
        baslik=raw["baslik"],
        tur=raw["tur"],
        hiyerarsi=int(raw["hiyerarsi"]),
        oncelik=raw["oncelik"],
        durum=raw["durum"],
        birim=list(raw.get("birim") or ["tum"]),
        duzey=list(raw.get("duzey") or []),
        yayim=_rg(raw.get("yayim")),
        degisiklikler=[r for r in (_rg(d) for d in raw.get("degisiklikler") or []) if r],
        kaynaklar=[Kaynak(**k) for k in raw.get("kaynaklar") or []],
        degisiklik_teyidi=(
            Teyit(_date(t["tarih"]), list(t["kaynaklar"])) if (t := raw.get("degisiklik_teyidi")) else None
        ),
        maddeler=[str(m) for m in raw["maddeler"]] if raw.get("maddeler") else None,
        zorunlu_ifadeler=list(raw.get("zorunlu_ifadeler") or []),
        capraz_bilinen_farklar={str(k): v for k, v in (raw.get("capraz_bilinen_farklar") or {}).items()},
        notlar=raw.get("notlar"),
    )


def load_manifest(path: Path = MANIFEST_PATH) -> list[Belge]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    belgeler = [_belge(b) for b in data.get("belgeler", [])]
    ids = [b.id for b in belgeler]
    if len(ids) != len(set(ids)):
        raise ValueError("Manifest'te yinelenen belge kimliği var")
    return belgeler


def load_lock(path: Path = LOCK_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_lock(lock: dict[str, dict[str, Any]], path: Path = LOCK_PATH) -> None:
    path.write_text(
        json.dumps(dict(sorted(lock.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
