"""Güncellik doğrulaması (plan 6.3, risk R1).

Kural özeti
  * İşlenmiş metin: PDF'teki Resmî Gazete tablosu manifest'teki yayım ve değişikliklerle aynı olmalı;
    tablodaki her değişikliğin metinde en az bir notu bulunmalı.
  * İlk yayım nüshası: manifest'te değişiklik olmamalı (olsaydı bu kopya eskimiş olurdu) ve
    "değişiklik yok" bilgisi başka bir kaynakla teyit edilip `degisiklik_teyidi` alanına yazılmalı.
    Teyit bir dönemden (TEYIT_GECERLILIK) eskiyse yenilenmesi istenir.
  * Yönergeler Resmî Gazete'de yayımlanmaz; güncellikleri KAYSİS'e dayanır.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from yonetmelik_asistani.ingest.extract import KONSOLIDE, RG_ILK_NUSHA, Extracted, split_maddeler
from yonetmelik_asistani.ingest.manifest import Belge

RG_TURLERI = ("kurum_yonetmeligi", "yok_yonetmeligi")
TEYIT_GECERLILIK = timedelta(days=183)  # bir dönem


def verify(b: Belge, ex: Extracted, today: date | None = None) -> list[str]:
    today = today or date.today()
    issues: list[str] = []
    if ex.image_pages:
        issues.append(
            f"sayfa {', '.join(map(str, ex.image_pages))}: resim var; tablo veya metin resim olarak "
            "gömülmüş olabilir (metin içeren başka bir kaynak kullanın)"
        )
    for phrase in b.zorunlu_ifadeler:
        if phrase not in ex.text:
            issues.append(f"metinde bulunması gereken ifade yok: {phrase!r}")
    if b.tur not in RG_TURLERI:
        return issues

    if ex.yayim is None and b.yayim and b.degisiklik_teyidi:
        # mevzuat.gov.tr değişmemiş yönetmeliklere tablo eklemez: yayım manifest'ten, teyitle
        return issues + _unchanged_checks(b, ex, today)
    if ex.yayim is None:
        return [*issues, "PDF'te Resmî Gazete tablosu da ilk yayım başlığı da yok; güncellik doğrulanamadı"]
    if b.yayim and ex.yayim != b.yayim:
        issues.append(f"yayım farklı: manifest {b.yayim}, PDF {ex.yayim}")
    elif not b.yayim:
        issues.append(f"manifest'te yayım bilgisi yok; PDF'e göre {ex.yayim}")

    if ex.bicim == KONSOLIDE:
        pdf_set, man_set = set(ex.degisiklikler), set(b.degisiklikler)
        for r in sorted(pdf_set - man_set, key=lambda r: r.tarih):
            issues.append(f"PDF'te olup manifest'te olmayan değişiklik: {r}")
        for r in sorted(man_set - pdf_set, key=lambda r: r.tarih):
            issues.append(f"manifest'teki değişiklik PDF'e işlenmemiş (KAYSİS eskimiş olabilir): {r}")
        for r in ex.degisiklikler:
            if ex.annotation_counts.get(r, 0) == 0:
                issues.append(f"{r} tabloda var ama metinde hiç değişiklik notu yok")
        for r in ex.annotation_counts:
            if r not in pdf_set:
                issues.append(f"metinde tabloda olmayan bir RG notu var: {r}")

    elif ex.bicim == RG_ILK_NUSHA:
        issues += _unchanged_checks(b, ex, today)
    return issues


def _unchanged_checks(b: Belge, ex: Extracted, today: date) -> list[str]:
    """Hiç değişmemiş olarak kullanılan (değişiklik notu taşımayan) metinlerin kontrolleri."""
    issues: list[str] = []
    if b.degisiklikler:
        issues.append("PDF değişiklikleri işlenmemiş metin ama manifest'te değişiklik var; kopya eskimiş: "
                      + ", ".join(map(str, b.degisiklikler)))
    teyit = b.degisiklik_teyidi
    if not teyit:
        issues.append("değişiklik olmadığı başka bir kaynakla teyit edilmeli (manifest: degisiklik_teyidi)")
    elif today - teyit.tarih > TEYIT_GECERLILIK:
        issues.append(f"değişiklik teyidi eski ({teyit.tarih:%d.%m.%Y}); yeniden kontrol edilmeli")
    if ex.annotation_counts:
        issues.append("değişmemiş sayılan metinde değişiklik notları var")
    return issues


# ---------------- çapraz kaynak karşılaştırması ----------------
_QUOTES = str.maketrans({"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"'})


def _canon(text: str) -> str:
    """Boşluk ve tırnak farklarını yok sayan karşılaştırma biçimi."""
    return re.sub(r"\s+", "", text.translate(_QUOTES))


@dataclass
class CrossCheck:
    ortak: int
    ayni: int
    yalniz_birincide: list[str] = field(default_factory=list)
    yalniz_ikincide: list[str] = field(default_factory=list)
    farkli: list[tuple[str, float]] = field(default_factory=list)  # (madde, benzerlik)
    bilinen: dict[str, str] = field(default_factory=dict)  # manifest'te açıklanmış farklar
    # Bilinen farklı maddelerde bile ikinci kaynaktaki her satır birincil metinde bulunmalı
    # (ör. ikinci kaynakta yalnızca resimler eksik): (madde, birincilde olmayan satır)
    eksik_satirlar: list[tuple[str, str]] = field(default_factory=list)

    @property
    def issues(self) -> list[str]:
        out = [f"md {k} yalnızca birincil kaynakta" for k in self.yalniz_birincide]
        out += [f"md {k} yalnızca ikinci kaynakta" for k in self.yalniz_ikincide]
        out += [f"md {k} kaynaklar arasında farklı (benzerlik {r:.3f})"
                for k, r in self.farkli if k not in self.bilinen]
        out += [f"md {k} bilinen fark olarak kayıtlı ama artık fark yok; manifest'ten silin"
                for k in self.bilinen if k not in dict(self.farkli)]
        out += [f"md {k}: ikinci kaynaktaki satır birincil metinde yok (içerik kaybı?): {line[:80]!r}"
                for k, line in self.eksik_satirlar]
        return out


def cross_check(primary_text: str, secondary_text: str,
                bilinen: dict[str, str] | None = None) -> CrossCheck:
    a, b = split_maddeler(primary_text), split_maddeler(secondary_text)
    common = [k for k in a if k in b]
    known = dict(bilinen or {})
    differing = []
    missing: list[tuple[str, str]] = []
    for k in common:
        ca, cb = _canon(a[k]), _canon(b[k])
        if ca != cb:
            differing.append((k, difflib.SequenceMatcher(None, ca, cb).ratio()))
            if k in known:
                missing += [(k, line) for line in b[k].split("\n")
                            if len(_canon(line)) > 20 and _canon(line) not in ca]
    return CrossCheck(
        ortak=len(common),
        ayni=len(common) - len(differing),
        yalniz_birincide=[k for k in a if k not in b],
        yalniz_ikincide=[k for k in b if k not in a],
        farkli=differing,
        bilinen=known,
        eksik_satirlar=missing,
    )
