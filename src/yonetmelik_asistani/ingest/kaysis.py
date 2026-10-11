"""KAYSİS istemcisi (plan 5.2, adım 2; karar K-09).

KAYSİS iki tuhaflık içerir:
  * Sunucu TLS zincirindeki ara sertifikayı (GeoTrust TLS RSA CA G1) göndermez. Doğrulamayı
    kapatmak yerine bu ara sertifika `certs/` altında depoya eklenmiştir; zincir yine
    DigiCert Global Root G2'ye kadar doğrulanır. Ara sertifika 2 Kasım 2027'de sona erer.
  * Belge adresleri ASP.NET çerez kontrolüyle yönlendirilir; çerez saklayan bir istemci gerekir.
"""

from __future__ import annotations

import html
import re
import ssl
from dataclasses import dataclass
from pathlib import Path

import certifi
import httpx

from yonetmelik_asistani.config import REPO_ROOT

BASE_URL = "https://kms.kaysis.gov.tr"
BUU_KURUM_ID = 92662996
INTERMEDIATE_CERT = REPO_ROOT / "certs" / "geotrust_tls_rsa_ca_g1.pem"

_SECTION_RE = re.compile(r'<a[^>]+href="#collapse\d+"[^>]*>(.*?)</a>', re.DOTALL)
_DOC_RE = re.compile(r'<a[^>]+href="https://kms\.kaysis\.gov\.tr/Home/Goster/(\d+)"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_COUNT_SUFFIX_RE = re.compile(r"\s+\d+$")


@dataclass(frozen=True)
class KaysisDocument:
    goster_id: int
    baslik: str
    bolum: str  # ör. "Kurum Yönetmelikleri", "Yönergeler"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/Home/Goster/{self.goster_id}"


def ssl_context(extra_cert: Path = INTERMEDIATE_CERT) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cafile=str(extra_cert))
    return ctx


def make_client(timeout_s: float = 90.0) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        verify=ssl_context(),
        follow_redirects=True,
        timeout=timeout_s,
        headers={"User-Agent": "Mozilla/5.0 (yonetmelik-asistani)"},
    )


def _clean(fragment: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub("", fragment)).split())


def parse_index(page_html: str) -> list[KaysisDocument]:
    """Kurum sayfasındaki belgeleri bölümleriyle birlikte çıkarır (tekil, sayfa sırasıyla)."""
    sections = [(m.start(), _COUNT_SUFFIX_RE.sub("", _clean(m.group(1))))
                for m in _SECTION_RE.finditer(page_html)]
    docs: dict[int, KaysisDocument] = {}
    for m in _DOC_RE.finditer(page_html):
        title = _clean(m.group(2))
        if not title:
            continue
        doc_id = int(m.group(1))
        before = [name for pos, name in sections if pos < m.start()]
        docs.setdefault(doc_id, KaysisDocument(doc_id, title, before[-1] if before else "?"))
    return list(docs.values())


def fetch_index(client: httpx.Client, kurum_id: int = BUU_KURUM_ID) -> list[KaysisDocument]:
    resp = client.get(f"/Home/Kurum/{kurum_id}")
    resp.raise_for_status()
    return parse_index(resp.text)


def fetch_document(client: httpx.Client, goster_id: int) -> tuple[bytes, str]:
    """Belgenin ham içeriği ve içerik türü. KAYSİS belgeleri genellikle PDF olarak verir."""
    resp = client.get(f"/Home/Goster/{goster_id}")
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "").split(";")[0].strip()
    if ctype == "text/html":
        raise RuntimeError(f"KAYSİS {goster_id}: belge yerine HTML sayfası döndü (çerez/yönlendirme)")
    return resp.content, ctype
