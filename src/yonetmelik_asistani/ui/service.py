"""Arayüzün çağırdığı servis: soru + profil → cevap ve kaynaklar (Faz 5).

Gradio'dan bağımsızdır; böylece arayüz mantığı GPU ve Gradio olmadan test edilebilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from yonetmelik_asistani.generation.pipeline import Answer, answer

# Profil seçenekleri: (görünen ad, manifestteki birim kimliği). Birim kimliği yalnızca birime özgü
# belgelerin süzülmesinde kullanılır; listede olmayan birimler için "tum" belgeleri yeterlidir.
BIRIMLER = [
    ("Belirtmek istemiyorum", None),
    ("Diş Hekimliği Fakültesi", "dis-hekimligi-fakultesi"),
    ("Eğitim Fakültesi", "egitim-fakultesi"),
    ("Fen-Edebiyat Fakültesi", "fen-edebiyat-fakultesi"),
    ("Mimarlık Fakültesi", "mimarlik-fakultesi"),
    ("Mühendislik Fakültesi", "muhendislik-fakultesi"),
    ("Tıp Fakültesi", "tip-fakultesi"),
    ("Veteriner Fakültesi", "veteriner-fakultesi"),
    ("Devlet Konservatuvarı", "devlet-konservatuvari"),
    ("Sağlık Hizmetleri MYO", "saglik-hizmetleri-myo"),
    ("Diğer meslek yüksekokulları", "myo"),
    ("Diğer fakülte / yüksekokul", None),
]
DUZEYLER = [("Lisans", "lisans"), ("Önlisans", "onlisans"), ("Hazırlık", "hazirlik")]

UYARI = ("Bu asistan Bursa Uludağ Üniversitesi'nin resmî hizmeti değildir. Cevaplar yürürlükteki "
         "mevzuata dayanır ama bağlayıcı değildir; kişisel durumunuz için birim öğrenci işlerine danışın.")

_LABEL_RE = re.compile(r"\[(K\d+)\]")


@dataclass
class Result:
    cevap: str
    kaynaklar: list[dict] = field(default_factory=list)  # yalnızca cevapta gösterilenler, sırayla
    ret: bool = False
    terim_notlari: list[str] = field(default_factory=list)
    sure_s: float | None = None


def cited_sources(a: Answer, maddeler: dict[str, dict]) -> list[dict]:
    order = list(dict.fromkeys(_LABEL_RE.findall(a.cevap)))
    by_label = {k["etiket"]: k for k in a.kaynaklar}
    out = []
    for label in order:
        k = by_label.get(label)
        if k is None:
            continue
        m = maddeler.get(k["madde_id"], {})
        out.append({"etiket": label, "baslik": m.get("path", k["baslik"]), "metin": m.get("text", ""),
                    "url": (m.get("meta") or {}).get("kaynak_url")})
    return out


@dataclass
class AssistantService:
    retriever: object
    llm: object
    maddeler: dict[str, dict]
    repealed: list = field(default_factory=list)
    budget: int = 5000
    rel_rerank: float = 0.1

    def ask(self, soru: str, *, birim: str | None = None, duzey: str | None = None) -> Result:
        soru = (soru or "").strip()
        if not soru:
            return Result("Lütfen bir soru yazın.")
        profile = {"birim": birim, "duzey": duzey}
        a = answer(soru, self.retriever, self.llm, self.maddeler, profile=profile, budget=self.budget,
                   rel_rerank=self.rel_rerank, repealed=self.repealed)
        return Result(a.cevap, [] if a.ret else cited_sources(a, self.maddeler), a.ret, a.terim_notlari, a.sure_s)


def render_sources(sources: list[dict]) -> str:
    if not sources:
        return ""
    parts = []
    for s in sources:
        link = f" · [resmî metin]({s['url']})" if s.get("url") else ""
        body = "\n".join(f"> {line}" for line in s["metin"].splitlines() if line.strip())
        parts.append(f"**[{s['etiket']}] {s['baslik']}**{link}\n\n{body}")
    return "\n\n---\n\n".join(parts)
