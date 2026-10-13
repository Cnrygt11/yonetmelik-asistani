"""Soru → arama → bağlam → cevap (plan 5.1 adım 6-7). Faz 4, sürüm 2.

Bağlam derleme kuralları:
  * Küçükten büyüğe: arama fıkra düzeyinde; maddesi `madde_tokens` altındaysa maddenin tamamı,
    değilse yalnızca bulunan parçalar bağlama girer. Aynı maddenin parçaları tek kaynakta toplanır.
  * Göreli eşik: reranker skoru en iyi kaynağın `rel_rerank` katının altındaki kaynaklar atılır
    (en iyi kaynak her zaman kalır). Mutlak eşik kullanılmaz: gerçek sorularda cevabı olan
    soruların yarısında en iyi skor 0,46'nın altında (FAZ_4.md).
  * Başlıkta belge türü, değişiklik notları, "Yalnızca: <birim>" ve kaldırılmış metne atıf uyarısı.
Bütçe dolunca eklemek durur.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from yonetmelik_asistani.generation.prompts import (
    ANSWER_SCHEMA_V3,
    ANSWER_SCHEMA_V4,
    DOGRULAMA_SCHEMA,
    EKSIK_CUMLESI,
    JSON_VERSIONS,
    PROMPT_VERSION,
    RET_CUMLESI,
    YENIDEN_YAZ_SCHEMA,
    ContextItem,
    build_check_messages,
    build_messages,
    build_rewrite_messages,
)
from yonetmelik_asistani.ingest.normalize import ascii_fold, turkish_lower
from yonetmelik_asistani.retrieval.hybrid import Hit

_LABEL_RE = re.compile(r"\[K(\d+)\]")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_ELLIPSIS_RE = re.compile(r"\.\.\.|…|\[\.\.\.\]")
_PUNCT_RE = re.compile(r"[^\w\s%]")
MIN_ALINTI = 15  # karakter; bundan kısa alıntı parçası ("Madde 5" gibi) kanıt sayılmaz
RET_YONLENDIRME = "Birim öğrenci işlerine başvurmanı öneririm."

TUR_ADI = {"kanun": "Kanun", "yok_yonetmeligi": "YÖK yönetmeliği", "kurum_yonetmeligi": "Yönetmelik",
           "senato_yonergesi": "Senato yönergesi", "birim_yonergesi": "Birim yönergesi",
           "usul_esas": "Usul ve esaslar"}


def approx_tokens(text: str) -> int:
    return len(text) // 4


def _norm(text: str) -> str:
    return ascii_fold(turkish_lower(" ".join(text.split())))


def load_maddeler(processed_dir: Path) -> dict[str, dict]:
    with (processed_dir / "maddeler.jsonl").open(encoding="utf-8") as f:
        return {m["madde_id"]: m for m in map(json.loads, f)}


@dataclass(frozen=True)
class Repealed:
    """Yürürlükten kaldırılmış bir metin ve ona atfı tanıyan kalıplar (RG sayısı, başlık)."""
    baslik: str
    kaldirilma: str
    yerine: str
    patterns: tuple[str, ...]


def load_repealed(manifest_path: Path) -> list[Repealed]:
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    titles = {b["id"]: b["baslik"] for b in data.get("belgeler", [])}
    out = []
    for k in data.get("kaldirilmis", []):
        kal = k.get("kaldirilma") or {}
        pats = [_norm(k["baslik"])]
        if (k.get("yayim") or {}).get("rg_sayi"):
            pats.append(str(k["yayim"]["rg_sayi"]))
        out.append(Repealed(k["baslik"], f"{kal.get('tarih', '?')} (RG {kal.get('rg_sayi', '?')})",
                            titles.get(k.get("yonlendir", ""), k.get("yonlendir", "")), tuple(pats)))
    return out


def repealed_refs(text: str, repealed: list[Repealed]) -> list[Repealed]:
    t = _norm(text)
    if "yururlukten kaldirilmistir" in t:  # kaldıran maddenin kendisi (ör. EÖY md. 44) atıf değildir
        return []
    return [r for r in repealed if any(p in t for p in r.patterns)]


def _header(madde: dict, repealed: list[Repealed]) -> str:
    meta = madde["meta"]
    parts = [madde["path"], f"[{TUR_ADI.get(meta.get('doc_type'), meta.get('doc_type', ''))}]"]
    birim = [b for b in meta.get("birim") or [] if b != "tum"]
    if birim:
        parts.append(f"[Yalnızca: {', '.join(birim)}]")
    notes = meta.get("degisiklik_notlari") or []
    if notes:
        parts.append("; ".join(notes))
    for r in repealed_refs(madde["text"], repealed):
        parts.append(f"[UYARI: bu madde {r.kaldirilma} tarihinde yürürlükten kaldırılan '{r.baslik}' "
                     f"metnine atıf yapıyor; yürürlükteki düzenleme: {r.yerine}]")
    return " · ".join(parts)


def load_links(path: Path) -> dict[str, list[str]]:
    """configs/ilgili_maddeler.yaml → {madde: [eklenecek maddeler]}."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return {e["madde"]: list(e["ekle"]) for e in data}


def build_context(hits: list[Hit], chunks: dict[str, dict], maddeler: dict[str, dict], *,
                  budget: int = 5000, madde_tokens: int = 1200, rel_rerank: float = 0.1,
                  max_sources: int | None = None, links: dict[str, list[str]] | None = None,
                  repealed: list[Repealed] | None = None) -> list[ContextItem]:
    """Bağlantılı madde, onu getiren maddenin hemen arkasına girer; parçası bulunmadığı için
    yalnızca `madde_tokens` altındaysa (tamamı) eklenir. Bütçe ve `max_sources` hepsine uygulanır."""
    repealed = repealed or []
    links = links or {}
    scores = [h.izler.get("rerank") for h in hits]
    if hits and all(s is not None for s in scores):
        top = max(scores)
        hits = [h for i, h in enumerate(hits) if i == 0 or h.izler["rerank"] >= rel_rerank * top]

    order: list[str] = []
    parts: dict[str, list[str]] = {}
    best: dict[str, float | None] = {}
    for h in hits:
        if h.madde_id not in parts:
            order.append(h.madde_id)
            parts[h.madde_id] = []
            best[h.madde_id] = h.izler.get("rerank")
        parts[h.madde_id].append(h.chunk_id)

    queue: list[tuple[str, str]] = []  # (madde, onu getiren madde ya da "")
    seen: set[str] = set()

    def add(mid: str, parent: str) -> None:
        if mid not in seen and mid in maddeler:
            seen.add(mid)
            queue.append((mid, parent))

    # aramada bulunan her madde kendi bağlantılarını getirir (daha önce bağlantı olarak girmiş olsa da);
    # yalnızca bağlantıyla gelen maddenin bağlantıları eklenmez (zincir olmasın)
    for mid in order:
        add(mid, "")
        for linked in links.get(mid, []):
            add(linked, mid)

    chunk_order = {c: i for i, c in enumerate(chunks)}
    items: list[ContextItem] = []
    used = 0
    for mid, parent in queue:
        if max_sources and len(items) >= max_sources:
            break
        madde = maddeler[mid]
        if approx_tokens(madde["text"]) <= madde_tokens:
            text = madde["text"]
        elif mid in parts:  # uzun madde (ör. 2547 md. 44): yalnızca bulunan fıkralar, belgedeki sırayla
            ids = sorted(parts[mid], key=chunk_order.__getitem__)
            text = "\n".join(chunks[c]["text"].partition("\n")[2] for c in ids)
        else:  # parçası bulunmamış uzun bağlantılı madde eklenmez
            continue
        cost = approx_tokens(text)
        if items and used + cost > budget:
            if parent:  # sığmayan bağlantılı madde atlanır, sıradaki bulunan madde denenir
                continue
            break
        items.append(ContextItem(f"K{len(items) + 1}", _header(madde, repealed), text, mid,
                                 rerank=best.get(mid), bagli=parent if mid not in parts else ""))
        used += cost
    return items


def term_notes(question: str, expander) -> list[str]:
    """Sözlükte eşleşen öğrenci ifadeleri için modele verilecek notlar."""
    if expander is None or not hasattr(expander, "matches"):
        return []
    return [f"Öğrencilerin '{e.ifadeler[0]}' dediği şey yönetmeliklerde '{', '.join(e.terimler)}' olarak geçer."
            for e in expander.matches(question)]


@dataclass
class Answer:
    soru: str
    cevap: str
    kaynaklar: list[dict]
    ret: bool
    karma: bool = False  # ret cümlesi ile kaynak etiketi birlikte (istem kuralı 4'e aykırı)
    eksik_belirtildi: bool = False
    etiket_hatalari: list[str] = field(default_factory=list)  # bağlamda olmayan [K#]
    etiketsiz: bool = False  # ret değilse ve hiç kaynak etiketi yoksa
    terim_notlari: list[str] = field(default_factory=list)
    ilk_rerank: float | None = None
    sure_s: float | None = None
    model: str | None = None
    istem: str = PROMPT_VERSION
    ham: str = ""  # v3: modelin JSON çıktısı (cevap alanı bundan oluşturulur)
    alintilar: list[dict] = field(default_factory=list)  # v3: {kaynak, metin, gecerli, bulundugu}
    json_hatasi: bool = False
    prompt_tokens: int | None = None
    yeniden_yazilan: str = ""  # takip sorusu tek başına anlaşılır hâle getirildiyse aramada kullanılan soru
    cikarilan: list[dict] = field(default_factory=list)  # destek kontrolünde çıkarılan cümleler {cumle, neden}


def check_answer(text: str, context: list[ContextItem]) -> dict:
    labels = {c.label for c in context}
    used = {f"K{n}" for n in _LABEL_RE.findall(text)}
    ret = RET_CUMLESI in text
    return {"ret": ret, "karma": ret and bool(used), "eksik_belirtildi": EKSIK_CUMLESI in text,
            "etiket_hatalari": sorted(used - labels), "etiketsiz": not ret and not used}


def _quote_norm(text: str) -> str:
    return " ".join(_PUNCT_RE.sub(" ", _norm(text)).split())


def verify_quote(metin: str, kaynak: str, context: list[ContextItem]) -> str | None:
    """Alıntının (… ile kısaltılmış parçalarıyla) geçtiği kaynağın etiketi; önce modelin yazdığı
    kaynakta, sonra diğerlerinde aranır. Noktalama, büyük-küçük harf ve Türkçe karakter farkı yok sayılır."""
    pieces = [_quote_norm(p) for p in _ELLIPSIS_RE.split(metin)]
    pieces = [p for p in pieces if len(p) >= MIN_ALINTI]
    if not pieces:
        return None
    ordered = sorted(context, key=lambda c: c.label != kaynak.strip("[] "))
    for c in ordered:
        body = _quote_norm(c.text)
        if all(p in body for p in pieces):
            return c.label
    return None


# Cümle sınırı: nokta/soru/ünlemden sonra boşluk ve büyük harf ya da etiket. "md. 18" ve "1.80" bölünmez.
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ\[(\"'])")
# v4: öğrencinin görmediği iç ifadeler (proje sahibinin notları); model kuralı kaçırırsa programla düzeltilir
_SADELE = [(re.compile(r"\bBağlamda\b"), "Yönetmeliklerde"), (re.compile(r"\bbağlamda\b"), "yönetmeliklerde"),
           (re.compile(r"\bMetinde\b"), "Yönetmelikte"), (re.compile(r"\bmetinde\b"), "yönetmelikte")]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]


def sadele(text: str) -> str:
    for pat, rep in _SADELE:
        text = pat.sub(rep, text)
    return text


@dataclass
class SupportChecker:
    """Cevap cümlelerini bağlamla karşılaştıran ikinci model çağrısı; desteklenmeyenleri döndürür."""
    llm: object
    context: list[ContextItem]
    wall_s: float = 0.0

    def __call__(self, sentences: list[str]) -> list[dict]:
        r = self.llm.chat(build_check_messages(sentences, self.context), schema=DOGRULAMA_SCHEMA, think=False,
                          max_tokens=600)
        self.wall_s += r.wall_s
        try:
            data = json.loads(r.text)
        except ValueError:
            return []
        out = data.get("desteklenmeyen") if isinstance(data, dict) else None
        return [x for x in out or [] if isinstance(x, dict) and isinstance(x.get("no"), int)]


def rewrite_question(question: str, history: list[tuple[str, str]], llm) -> tuple[str, float]:
    """Takip sorusunu son iki tura bakarak tek başına anlaşılır hâle getirir → (soru, süre)."""
    if not history:
        return question, 0.0
    r = llm.chat(build_rewrite_messages(question, history[-2:]), schema=YENIDEN_YAZ_SCHEMA, think=False,
                 max_tokens=200)
    try:
        data = json.loads(r.text)
    except ValueError:
        data = None
    soru = str(data.get("soru") or "").strip() if isinstance(data, dict) else ""
    return (soru or question), r.wall_s


def render(raw: str, context: list[ContextItem], checker=None, sade: bool = False
           ) -> tuple[str, list[dict], bool, list[dict]]:
    """JSON çıktısından (v3/v4) öğrenciye gösterilecek metni kurar → (metin, alıntılar, json_hatasi, çıkarılan).
    Doğrulanan alıntı yoksa, model ret ettiyse ya da destek kontrolü ana cevabın bütün cümlelerini
    çıkardıysa metin ret cümlesidir."""
    ret = f"{RET_CUMLESI} {RET_YONLENDIRME}"
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return ret, [], True, []
    quotes = []
    for q in data.get("alintilar") or []:
        if not isinstance(q, dict):
            continue
        found = verify_quote(str(q.get("metin", "")), str(q.get("kaynak", "")), context)
        quotes.append({"kaynak": q.get("kaynak"), "metin": q.get("metin"), "gecerli": found is not None,
                       "bulundugu": found})
    valid = [q for q in quotes if q["gecerli"]]
    cevap = str(data.get("cevap") or "").strip()
    if not valid or RET_CUMLESI in cevap:
        return ret, quotes, False, []
    main = split_sentences(cevap)
    details = [str(a).strip() for a in data.get("ayrintilar") or [] if str(a).strip()]
    removed: list[dict] = []
    if checker is not None:
        flagged = {f["no"]: str(f.get("neden", "")) for f in checker(main + details)}
        removed = [{"cumle": s, "neden": flagged[i]} for i, s in enumerate(main + details) if i in flagged]
        details = [d for j, d in enumerate(details) if len(main) + j not in flagged]
        main = [s for i, s in enumerate(main) if i not in flagged]
        if not main:
            return ret, quotes, False, removed
    cevap = " ".join(main)
    if not _LABEL_RE.search(cevap):  # etiket unutulduysa doğrulanan alıntıların kaynakları eklenir
        cevap += " " + "".join(f"[{lab}]" for lab in dict.fromkeys(q["bulundugu"] for q in valid))
    lines = [cevap] + [f"- {d}" for d in details]
    if data.get("eksik") and EKSIK_CUMLESI not in cevap:
        lines.append(f"{EKSIK_CUMLESI} Bu kısım için birim öğrenci işlerine başvurabilirsin.")
    text = "\n".join(lines)
    return (sadele(text) if sade else text), quotes, False, removed


def render_v3(raw: str, context: list[ContextItem]) -> tuple[str, list[dict], bool]:
    """v3 çıktısı, destek kontrolü olmadan → (metin, alıntılar, json_hatasi)."""
    return render(raw, context)[:3]


def answer(question: str, retriever, llm, maddeler: dict[str, dict], *, profile: dict | None = None,
           budget: int = 5000, rel_rerank: float = 0.1, max_sources: int | None = None,
           links: dict[str, list[str]] | None = None, repealed: list[Repealed] | None = None,
           istem: str = PROMPT_VERSION, think: bool | None = None, max_tokens: int | None = None,
           dogrula: bool = False, gecmis: list[tuple[str, str]] | None = None) -> Answer:
    """gecmis: aynı oturumdaki önceki (soru, cevap) çiftleri; varsa soru önce tek başına anlaşılır hâle getirilir.
    dogrula: JSON istemlerinde cevap cümleleri ikinci bir model çağrısıyla bağlama karşı denetlenir."""
    aranan, rewrite_s = rewrite_question(question, gecmis or [], llm) if gecmis else (question, 0.0)
    hits = retriever.search(aranan, profile=profile, mode="hybrid_rerank")
    context = build_context(hits, retriever.chunks, maddeler, budget=budget, rel_rerank=rel_rerank,
                            max_sources=max_sources, links=links, repealed=repealed)
    notes = term_notes(aranan, getattr(retriever, "expander", None))
    profile = profile or {}
    messages = build_messages(aranan, context, duzey=profile.get("duzey") or "belirtilmedi",
                              birim=profile.get("birim") or "belirtilmedi", terim_notlari=notes, istem=istem)
    schema = {"v3": ANSWER_SCHEMA_V3, "v4": ANSWER_SCHEMA_V4}.get(istem)
    result = llm.chat(messages, schema=schema, think=think, max_tokens=max_tokens)
    checker = SupportChecker(llm, context) if dogrula and istem in JSON_VERSIONS else None
    if istem in JSON_VERSIONS:
        text, quotes, json_err, removed = render(result.text, context, checker, sade=istem == "v4")
    else:
        text, quotes, json_err, removed = result.text, [], False, []
    checks = check_answer(text, context)
    wall = result.wall_s + rewrite_s + (checker.wall_s if checker else 0.0)
    return Answer(
        soru=question, cevap=text, terim_notlari=notes, **checks,
        kaynaklar=[{"etiket": c.label, "madde_id": c.madde_id, "baslik": c.header, "token": approx_tokens(c.text),
                    "rerank": c.rerank, "bagli": c.bagli} for c in context],
        ilk_rerank=hits[0].izler.get("rerank") if hits else None,
        sure_s=round(wall, 1), model=result.model, istem=istem,
        ham=result.text if istem in JSON_VERSIONS else "", alintilar=quotes, json_hatasi=json_err,
        prompt_tokens=result.prompt_tokens, yeniden_yazilan=aranan if aranan != question else "",
        cikarilan=removed,
    )


def numbers_covered(alinti: str | None, cevap: str) -> float | None:
    """Altın alıntıdaki sayıların cevapta geçme oranı (otomatik ön kontrol; süre ve oranlar)."""
    nums = set(_NUM_RE.findall(alinti or ""))
    if not nums:
        return None
    found = set(_NUM_RE.findall(cevap))
    return round(len(nums & found) / len(nums), 2)
