# Faz 2 · Parçalama ve indeks (4–5. haftalar)

Plan bölüm 13: madde ayrıştırıcı, metadata, BM25 ve BGE-M3 indeksleri, Qdrant.
**Çıktı:** indeks v1, arama komut satırı aracı.
**Çıkış ölçütü (M2):** ayrıştırıcı testleri geçti, Recall@5 ölçüldü.

## Komutlar

```bash
uv sync --extra ingest --extra search
python -m yonetmelik_asistani.chunking       # chunks.jsonl + maddeler.jsonl
python -m yonetmelik_asistani.index          # BM25 + BGE-M3/Qdrant (--no-dense: yalnız BM25)
python eval/run_eval.py                      # geliştirme seti; --split test yalnızca kilometre taşlarında
python eval/run_eval.py --methods bm25,dense,hybrid,hybrid_rerank   # GPU
```

Colab `.gov.tr` adreslerini çözemiyor (12.10.2026: `Temporary failure in name resolution`).
İndirme ve çapraz kontrol yerelde yapılır; yerel `data/raw` Drive'a yüklenir, `extract` her dosyanın
sha256 özetini `configs/corpus_lock.json` ile karşılaştırır. Notebook 6.1 internete çıkmaz, yalnızca `extract` çalıştırır.

Karar K-10: BM25 belirteci **F5** (ilk 5 harf); Snowball'dan 10 puan iyi ölçüldü. Plan PyStemmer
öneriyordu; aynı Snowball algoritması saf Python `snowballstemmer` ile karşılaştırmada kaldı.

## Kontrol listesi

### Parçalama
- [x] Ayrıştırıcı: Bölüm › Madde › Fıkra; madde başlıkları, değişiklik notları, iç atıflar
- [x] Parçalayıcı: kısa madde bütün, uzun madde fıkra, çok uzun fıkra bent/cümle sınırından bölünür;
      başlık yolu her parçada; tablolar bölünmez; yinelenen resmî fıkra numaraları ayrışır (`f4-2`)
- [x] P1 derlem: **152 madde, 318 parça**, en uzun parça ~510 token
- [x] Parçalama sırasında bulunan metin çıkarma hataları düzeltildi (aşağıda)

### İndeks ve arama
- [x] BM25: üç belirteç (F5 ilk 5 harf, Snowball, karakter n-gram)
- [x] BGE-M3 yoğun vektörler + Qdrant: kod hazır (`index/dense.py`), Colab'da ölçülecek
- [x] RRF birleştirme ve bge-reranker-v2-m3: kod hazır, sahte modellerle test edildi
- [x] Metadata filtresi (yürürlük, düzey, birim) iki aramada da aynı kuralla
- [x] Arama komut satırı aracı: `python -m yonetmelik_asistani.retrieval "soru"`
- [ ] Colab T4'te dört kipin ölçümü (notebook bölüm 6)

### Değerlendirme
- [x] Başlangıç altın seti: 32 soru (29 cevaplı, 3 cevapsız); alıntılar programla doğrulanıyor
- [ ] Altın setin ikinci geçişi (proje sahibi, ilk geçişten en az 48 saat sonra)
- [x] İlk Recall@5 ölçümü (M2 taban çizgisi)
- [ ] **M2 → Faz 3/4**

## İlk ölçüm · 12.10.2026 · tüm set (29 cevaplı soru)

| Yöntem | Recall@5 | MRR@10 |
|---|---|---|
| BM25 + F5 | **0,828** | 0,603 |
| BM25 + Snowball | 0,724 | 0,641 |
| BM25 + karakter n-gram | 0,793 | 0,612 |

Geliştirme seti taban çizgisi (17 cevaplı): BM25 F5 Recall@5 **0,706**.
Kaçırılanların tamamı kelime uyuşmazlığı: "dönem"/yarıyıl, "harç"/katkı payı, "atılmak"/ilişik
kesme, "tek ders"/ek sınav. Yoğun arama ve öğrenci dili sözlüğü bu açığı hedefliyor.

## Faz 2'de bulunan ve düzeltilen metin çıkarma hataları

| Sorun | Etki | Düzeltme |
|---|---|---|
| Tabloyla aynı PDF bloğundaki paragraf atılıyordu | YDYO md. 8/5 tamamen kayıp | Tablo ayıklaması satır düzeyinde |
| Bilinen fark muafiyeti çok genişti | Yukarıdaki kayıp çapraz kontrolden kaçtı | İkinci kaynağın her satırı birincilde aranıyor |
| Sayfa numaraları metne karışıyordu | "2 tarafından…" gibi bozuk satırlar | Kenardaki tek sayılar ayıklanıyor |
| Sayfa başlığı cümle içine giriyordu | "…son yükseköğretim Senato Karar Eki kurumundaki…" | Birden fazla sayfada tekrar eden kenar satırları ayıklanıyor |
| İki satırlı başlık önceki paragrafa yapışıyordu | 2547 md. 44 başlığı "ve sınavlar:" | Başlık başı geri alınıyor; dipnot numaraları temizleniyor |

Resmî metindeki bir numaralandırma hatası da kayda geçti: YDYO md. 8'de iki ayrı (4) numaralı
fıkra var (KAYSİS ve mevzuat.gov.tr'de aynı).
