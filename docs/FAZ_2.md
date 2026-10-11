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
- [x] Colab T4'te dört kipin ölçümü (notebook bölüm 6)

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

## Dört kip · 12.10.2026 · Colab T4 · geliştirme seti (17 cevaplı, 3 cevapsız)

| Kip | Recall@5 | MRR@10 | Kaçırılan | İlk skor: cevaplı medyan / cevapsız |
|---|---|---|---|---|
| BM25 F5 | 0,706 | 0,577 | q-010, q-011, q-012, q-016, q-022 | 5,09 / 2,13–2,69 |
| BGE-M3 (dense) | **1,000** | **0,855** | – | 0,636 / 0,425–0,527 (kosinüs) |
| Hibrit (RRF) | 0,824 | 0,783 | q-011, q-012, q-016 | RRF, ayırt etmiyor |
| Hibrit + reranker | 0,882 | 0,749 | q-011, q-016 | **0,915 / 0,001–0,013** |

- Yoğun arama kelime uyuşmazlığını tek başına çözdü; RRF, BM25'in yanlış adaylarıyla onu aşağı çekti.
- Reranker'ın kaçırdığı iki soru da öğrenci dili: "tek ders" (ek sınav), "harç/atılmak" (katkı payı,
  ilişik kesme). Plan bu açığı öğrenci dili sözlüğüyle kapatıyor (`data/glossary.yaml`, Faz 6).
- Reranker skoru cevaplı ve cevapsız soruları açık farkla ayırıyor (0,92'ye karşı ≤0,013): ret
  eşiği (FR-07, Faz 4) için en güçlü sinyal.
- Fark 17 soruda 2 soru; karar için küçük. Kip seçimi 150 soruluk sette yeniden ölçülecek.

Karar K-11: Plan hattı (hibrit + reranker) korunur; ret eşiği reranker skoruna kalibre edilir.
Altın set 150 soruya ulaşınca ve sözlük bağlanınca dense ile yeniden karşılaştırılır.

Colab notu: değerlendirmede GPU'nun ~11 GiB'ı PyTorch dışında doluyordu. Neden: `bm25s` içe
aktarılırken bir JAX işlemi çalıştırıyor; Colab'da hazır kurulu JAX da GPU'yu ilk kullanımda
belleğin %75'ini ayırıyor. JAX artık işlemciyle sınırlanıyor (`JAX_PLATFORMS=cpu`). Ölçüm: BGE-M3 +
reranker birlikte ~2,6 GiB; Colab'da doğrulandı (reranker öncesi 11,8 GiB boş), Qwen3.5-9B için yer var.

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

## Faz 3'e devredilenler (12.10.2026)

- **Güncellik açığı · 7592 sayılı Kanun (RG 9/8/2026):** 2547 md. 44'teki değişiklik derlemde var
  (indirme 11.10.2026). Ama öğrenim affını getiren **geçici md. 85** derlem dışında; manifest yalnızca
  md. 44 ve 54'ü alıyor. Bahar başvurusu 9.12.2026'da kapanıyor. Ayrıştırıcının "Geçici Madde N-"
  biçimini tanıması ve manifestin geçici maddeleri seçebilmesi gerekiyor.
- **Fakülteye özgü kurallar:** P2'de Tıp, Diş Hekimliği, Veteriner ve Konservatuvarın kendi
  eğitim-sınav yönergeleri, Mühendislik ve Mimarlık gibi birimlerin staj/bitirme yönergeleri var.
  Profil filtresi (FR-04) birim belirtilince başka birimin belgesini dışarıda bırakıyor; birim
  belirtilmezse bırakmıyor. P2 belgeleri eklenmeden önce: bağlam başlığında "Yalnızca: <birim>"
  etiketi, istemde "birime özgü kuralı genel kural gibi sunma" kuralı, arayüzde profil sorusu ve
  bunları sınayan altın set soruları.
- **Gerçek soru kaynakları:** Merkezî bir ÖİDB SSS sayfası bulunamadı. Aday kaynaklar: SHMYO SSS
  (2025), ÖİDB duyuruları (kayıt yenileme, ÇAP, yan dal, öğrenim affı), öğrenci forumları.
- **Uçtan uca deneme:** `eval/e2e_deneme.py`, notebook bölüm 7.

