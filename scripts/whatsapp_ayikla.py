"""WhatsApp dışa aktarımlarından mevzuat sorusu adaylarını ayıklar ve anonimleştirir.

    python scripts/whatsapp_ayikla.py data/private/whatsapp/*.txt -o data/private/whatsapp/adaylar.jsonl

Gönderen adı hiçbir zaman çıktıya yazılmaz. Sistem satırları (katıldı, ekledi...) atılır.
Telefon, e-posta, bağlantı, @etiket, uzun sayı (öğrenci no) ve "X hoca" kalıbındaki adlar maskelenir.
Çıktı yine data/private altında kalır; depoya yalnızca elle gözden geçirilmiş sorular girer.
Belirli bir derse veya hocanın takdirine bağlı sorular sonraki elle eleme adımında çıkarılır.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yonetmelik_asistani.ingest.normalize import turkish_lower

MSG_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4}) (\d{2}):(\d{2}) - ([^:]{1,60}): (.*)$")
SYS_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4} \d{2}:\d{2} - [^:]*$")  # iki nokta yok: sistem satırı

MASKS = [
    (re.compile(r"https?://\S+|www\.\S+"), "<BAĞLANTI>"),
    (re.compile(r"\S+@\S+\.\S+"), "<EPOSTA>"),
    (re.compile(r"@\u2068?[^\s\u2069]+\u2069?|@\d+"), "<ETİKET>"),
    (re.compile(r"(\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"), "<TELEFON>"),
    (re.compile(r"\b\d{6,}\b"), "<NUMARA>"),
    # "Ahmet hoca", "ahmet hocaya", "Ali Bey", "Ayşe Hanım"
    (re.compile(r"\b[A-ZÇĞİÖŞÜa-zçğıöşü]{2,}\s+(?=(hoca|bey|hanım)\w*\b)", re.IGNORECASE), "<AD> "),
]
SKIP_BODIES = ("<Medya dahil edilmedi>", "Bu mesaj silindi", "null", "<Bu mesaj düzenlendi>")

# Mevzuat konuları (küçük harf, Türkçe karakterli ve karaktersiz biçimler)
TOPIC = re.compile(
    r"devams[iı]z|b[uü]t[uü]?n?leme|\bb[uü]t\b|ek s[iı]nav|tek ders|mazeret|rapor|yatay ge[cç]|"
    r"\b[cç]ap\b|yan ?dal|kayd[iı]? ?(dondur|sil|yenile)|kay[iı]t (dondur|sil|yenile)|dondur|"
    r"har[cç]|katk[iı] pay|azami|mezun|transkript|ortalama|\bgano\b|\bagno\b|\b(ff|fd|dd|dc|cc|dz)\b|"
    r"yaz okul|yaz [oö][gğ]retim|muaf|haz[iı]rl[iı]k|intibak|kredi|\bakts\b|itiraz|disiplin|kopya|"
    r"[uü]stten|alttan|ders y[uü]k|s[iı]n[iı]rs[iı]z|onur|ders kayd|ders se[cç]|ekle ?b[iı]rak|"
    r"[iı]li[sş]i[kğ]|uzaklaşt|uzaklast|ilişik|y[oö]netmeli[kğ]|y[oö]nerge|harf not|ge[cç]me not|"
    r"ko[sş]ullu|[sş]artl[iı]|izinli|kay[iı]t hakk"
)
QUESTION = re.compile(r"\?|\b(m[iıuü]|m[iıuü]s[iı]n|m[iıuü]y[iı]z|m[iıuü]d[iı]r|nas[iı]l|ka[cç]|ne zaman|"
                      r"neden|ni[cç]in|hangi|kim|nereye|nereden|var m[iı]|olur mu)\b")


def mask(text: str) -> str:
    for rx, repl in MASKS:
        text = rx.sub(repl, text)
    return text


def parse(path: Path):
    """(yıl-ay, metin) çiftleri; çok satırlı mesajlar birleştirilir, gönderen atılır."""
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.lstrip("\u200e\u200f")
        m = MSG_RE.match(line)
        if m:
            if cur:
                yield cur
            cur = [f"{m.group(3)}-{int(m.group(2)):02d}", m.group(7)]
        elif SYS_RE.match(line):
            if cur:
                yield cur
            cur = None
        elif cur:
            cur[1] += " " + line
    if cur:
        yield cur


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args(argv)

    seen: set[str] = set()
    out, stats = [], Counter()
    for f in args.files:
        for ym, body in parse(f):
            stats["mesaj"] += 1
            body = body.strip()
            if not body or any(s in body for s in SKIP_BODIES):
                continue
            low = turkish_lower(body)
            if not (TOPIC.search(low) and QUESTION.search(low)):
                continue
            stats["aday"] += 1
            text = mask(" ".join(body.split()))
            key = re.sub(r"\W+", "", turkish_lower(text))
            if key in seen or len(text) < 15:
                continue
            seen.add(key)
            out.append({"ay": ym, "metin": text})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{stats['mesaj']} mesaj → {stats['aday']} aday → {len(out)} tekil → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
