# Faz 4 · Üretim ve denetim (plan: 6–7. haftalar)

Plan bölüm 13: sistem istemi, bağlam derleme, LLM istemcisi, çıktı denetimi, ret eşiği
kalibrasyonu. **Çıktı:** uçtan uca MVP (notebook).
**Çıkış ölçütü (M3):** geliştirme setinde ilk tam ölçüm.
Hedefler (plan 1): %85 doğru cevap, %95 doğru atıf, cevapsız soruların %90'ında doğru ret.

## Kontrol listesi

- [x] **Öğrenci dili sözlüğü aramaya bağlandı (K-12).** `retrieval/glossary.py`; genişletilmiş
      soru BM25, BGE-M3 ve reranker'a aynı biçimde verilir; Türkçe karaktere duyarsız.
- [x] Colab T4'te 196 soruyla dört arama kipi, sözlüklü ve sözlüksüz (notebook 6.2-6.3)
- [x] Bağlam derleme v2: göreli reranker eşiği (en iyi kaynağın %10'u), belge türü, "Yalnızca:
      <birim>" etiketi, kaldırılmış metne atıf uyarısı (EÖY md. 20, Yaz Öğr. md. 7/13/14, YDYO
      md. 15/24; kaldıran madde EÖY md. 44 hariç)
- [x] İstem v2 (`PROMPT_VERSION`): karma ret yasağı ve "Bu ayrıntı yönetmeliklerde yer almıyor",
      terim eşdeğerliği yalnızca sözlük notlarından ve bağlamdan, ilk cümlede istisna, birime özgü
      kaynak, kaldırılmış metin, norm çatışması
- [x] Çıktı denetimi: karma ret, eksik bilgi cümlesi, geçersiz/eksik etiket, alıntıdaki sayıların
      cevapta geçme oranı (`eval/run_answers.py`, notebook bölüm 8)
- [x] Cevap puanlama: `eval/score_answers.py`; 134 cevap elle puanlandı (`eval/reports/puanlar_gelistirme_v2.jsonl`)
- [ ] Ret eşiği kalibrasyonu (sözlük bağlandıktan sonra)
- [x] **M3: geliştirme setinde ilk tam ölçüm (12.10.2026)** — hedeflerin altında, aşağıda

## Sözlük ölçümü · 12.10.2026 · BM25 karakter n-gram · geliştirme (134 soru)

| | Recall@5 | MRR@10 |
|---|---|---|
| Sözlüksüz | 0,730 | 0,547 |
| İlk sözlük (28 kayıt) | 0,787 | 0,609 |
| **Kural uygulanmış sözlük (24 kayıt)** | **0,811** | **0,614** |

İlk sözlük 10 soruyu kazandırdı, 4 soruyu (wa-023, wa-041, wa-064, sy-050) kaybettirdi. Neden:
"ortalama", "ders seçimi" gibi belgelerde de geçen kelimeler genişletilince ilgisiz maddeler öne
çıkıyordu. Kural: **belgelerde 3'ten fazla geçen ifade öğrenci jargonu değildir, sözlüğe girmez.**
Kural geliştirme setindeki hatalardan çıkarıldı; genellenip genellenmediğini kilitli test
gösterecek.

## Dört kip, sözlüklü ve sözlüksüz · 12.10.2026 · Colab T4 · geliştirme (134 soru)

| Kip | Recall@5 | MRR@10 | + sözlük Recall@5 | + sözlük MRR@10 |
|---|---|---|---|---|
| BM25 (karakter n-gram) | 0,730 | 0,547 | 0,811 | 0,614 |
| BGE-M3 | 0,803 | 0,604 | 0,861 | 0,653 |
| Hibrit (RRF) | 0,779 | 0,639 | 0,836 | 0,702 |
| **Hibrit + reranker** | 0,820 | 0,652 | **0,885** | **0,720** |

- **K-11 doğrulandı:** plan hattı (hibrit + reranker) sözlükle en iyi kip. 17 soruluk ilk sette
  önde görünen tek başına BGE-M3, gerçek sorularda geride.
- Sözlük her kipte 5-8 puan kazandırıyor; yalnızca BM25'e uydurulmadığının işareti.
- **Ret sinyali zayıfladı:** reranker'ın ilk skor medyanı cevaplı sorularda 0,457 (17 soruluk
  sette 0,915); 12 cevapsız sorudan 11'i 0,04'ün altında, biri 0,450. Tek eşikle ret, küçük
  setteki kadar temiz olmayacak. BGE-M3 skoru ret için işe yaramıyor (cevaplı 0,62, cevapsız
  0,43-0,62).

**Altın set düzeltmesi:** hep kaçırılan 14 sorudan altısında altın madde listesi dardı; altın
cevapta kaynak gösterilen madde listeye yazılmamıştı (wa-011, wa-021, wa-025, wa-058, wa-066,
wa-068). Kural: altın cevapta kaynak gösterilen her madde altın maddeler listesinde olmalı.
Düzeltme sonrası BM25 + sözlük 0,811 → 0,828 (yerel); Colab sayıları bir sonraki ölçümde
güncellenecek.

## M3 · ilk tam ölçüm · 12.10.2026 · istem v2 · Qwen3.5-9B Q4 · geliştirme (134 soru)

| Ölçüt | Sonuç | Hedef |
|---|---|---|
| Doğru cevap (122 cevaplı soru) | **%45,9** (kısmen %34,4, yanlış %19,7) | %85 |
| Doğru atıf (kaynak gösteren cevaplar) | **%94,8** | %95 |
| Doğru ret (12 cevapsız soru) | **%100** | %90 |
| Altın madde bağlamda | %92,6 | – |
| Cevap süresi (medyan) | 14,8 sn | – |

Kaynağa göre doğru cevap: ilk set (benim yazdığım) **14/17**, sentetik 22/33, WhatsApp **20/72**.
Kategoriye göre: tek madde %63, koşul/istisna %44, kısmi %36, çok madde %18, yanlış önkabul %0 (n=5).

**Hata analizi:**
- Sorun ağırlıkla **okumada**, aramada değil: altın madde bağlamdayken 113 sorunun 58'i kısmen
  doğru ya da yanlış. Bağlamda değilken (9 soru) 8'i başarısız.
- **Gürültülü bağlam:** medyan 4 kaynak; model ilgisiz kaynakları karıştırıyor (ör. Muafiyet
  Yönergesi'nin ağırlıklı ortalama hesabını harf notu hesabı sanmak, YDYO muafiyet tablosunu bölüm
  derslerine uygulamak, FD'yi "koşullu geçer" saymak).
- **Uzunluk:** doğru cevapların medyanı 750, kısmen/yanlış cevapların ~1.050-1.100 karakter;
  gereksiz maddeler hata getiriyor.
- **"Bu ayrıntı yönetmeliklerde yer almıyor" aşırı kullanımı:** cevaplı soruların %34'ünde; bunların
  yalnızca 8/41'i doğru. Kural 4 modeli her cevaba bu cümleyi eklemeye itiyor.
- **İstem sızıntısı:** birkaç cevapta istem kuralları cevaba kopyalanmış (wa-041, wa-069).
- Karma ret 6 cevapta.
- Ret davranışı iyi: 12 cevapsız sorunun hepsinde uydurmadan ret veya yönlendirme (otomatik ön
  kontrol %33 diyordu; model ret cümlesi yerine "yer almıyor" cümlesini kullanıyor).
- Model belirli bir maddeyi bulamadığında (md. 35 koşullu geçme, md. 18 devamsızlık) yakın
  maddelerden yanlış genelleme yapıyor.

**Altın set düzeltmeleri (model haklı çıktı, metinden doğrulandı):** q-028 ve sy-007 (kopya çekmek
2547 md. 54/1-**c**: bir yarıyıl uzaklaştırma; altın cevapta bir haftadan bir aya yazıyordu), sy-017
(aynı nedenle), sy-038 (yatay geçiş takvimi Geçiş Yön. md. 5/3-4'te Ocak/Temmuz; altın cevapta
"yazmaz" deniyordu). Düzeltmeler cevaplar görüldükten sonra yapıldı, ama her biri kaynak metne
dayanıyor.

**Sonraki adımlar (önem sırasıyla):** bağlamı daraltmak (daha sıkı göreli eşik, en çok 3 kaynak),
istemi kısaltmak ve "yer almıyor" cümlesini yalnızca gerçekten eksik bilgi olduğunda kullandırmak,
cevap uzunluğunu sınırlamak, Qwen'in düşünme kipini (think) bir alt kümede denemek; ardından istem
v3 ile yeniden ölçüm.

## İyileştirme planı · Adım 1-2 · hazırlık (12.10.2026)

M3 analizine göre sorun ikili: altın maddelerin **tamamı** bağlamda yalnızca cevaplı soruların
%73'ünde (en çok eksik: EÖY md. 35, YDYO md. 24, EÖY md. 18), tamamı varken de kaynak sayısı arttıkça
doğruluk düşüyor (1-2 kaynakta %96, 5-6 kaynakta %41). Kararlar: şimdilik belge eklenmez, soruya
özgü ayar yapılmaz, %85 hedefi değişmez. Büyük model veya LoRA ancak bu iki adım yetmezse (Adım 3).

**Adım 1 · bağlam:**
- `configs/ilgili_maddeler.yaml`: bağlantılı maddeler. Bir madde bağlama girerse, onsuz yanlış
  okunacak madde de hemen arkasına eklenir (EÖY md. 32 ↔ 35; EÖY md. 22 ↔ YDYO md. 23-24; YDYO md. 7 →
  md. 8, çünkü md. 7/4'ün tabloları resmî metinde md. 8'in içinde basılı). Kural sözlükteki gibi
  yapısaldır: sorulara göre değil, belgelerin yapısına göre yazılır.
- `build_context`: `max_sources` (en çok kaynak) ve bağlantılı maddeler; kaynaklara rerank skoru ve
  "bağlı" bilgisi yazılır.
- `eval/dump_candidates.py` (Colab, LLM yok) ilk 20 adayı skorlarıyla döker; `eval/sweep_context.py`
  (yerel) k, göreli/mutlak eşik, en çok kaynak ve bağlantı ızgarasını tarar ("tamamı bağlamda" ile
  gürültü arasındaki Pareto sınırı). Yalnız BM25 ile yerel deneme: bağlantılar "tamamı bağlamda"
  oranını 0,639'dan 0,697'ye çıkarıyor (gerçek ölçüm reranker skorlarıyla Colab dökümünde).

**Adım 2 · istem v3:** model önce soruyu cevaplayan cümleleri bağlamdan aynen kopyalar (JSON:
alıntılar → 1-2 cümlelik cevap → en çok 3 ayrıntı → eksik). Alıntılar programla bağlamda aranır
(büyük-küçük harf, noktalama ve Türkçe karakter farkı yok sayılır; "…" ile kısaltma kabul); doğrulanan
alıntı yoksa cevap verilmez. Karşılaştırma sabit 40 soruda (`eval/alt_set_40.txt`, 34 cevaplı + 6
cevapsız, kimlik özetiyle seçildi; v2 burada 16/34 doğru, 6/6 doğru ret): v3 düşünme kapalı ve açık.

## Adım 1 · bağlam taraması · 12.10.2026 · Colab dökümü (reranker skorlarıyla) · geliştirme (134 soru)

Başlangıç çizgisi M3'ü birebir verdi (tamamı bağlamda 0,730 = 89/122), döküm ve tarama tutarlı.

| Ayar | Tamamı bağlamda | En az biri | Kaynak | Gürültü | Cevapsızda kaynak |
|---|---|---|---|---|---|
| M3: k=6, göreli 0,1 | 0,730 | 0,934 | 3,77 | 2,74 | 4,42 |
| + bağlantılı maddeler | 0,779 | 0,934 | 4,14 | 3,06 | 4,67 |
| **+ bağlantılı, en çok 5 kaynak (seçilen)** | **0,770** | **0,934** | **3,84** | **2,77** | **4,17** |
| k=8, bağlantılı, en çok 5 | 0,787 | 0,934 | 4,07 | 2,98 | 4,67 |
| k=6, göreli 0,2, bağlantılı, en çok 4 | 0,721 | 0,877 | 3,03 | 2,03 | 3,08 |
| k=12, göreli 0,05, bağlantılı | 0,861 | 0,967 | 6,94 | 5,75 | 8,00 |

Ödünleşim açık: "tamamı bağlamda" oranını artıran her ayar gürültüyü de artırıyor; gürültüyü azaltanlar
altın maddeyi de dışarıda bırakıyor (mutlak eşik ve sıkı göreli eşik "en az biri" oranını 0,93'ten
0,81-0,88'e düşürüyor). Seçilen ayar gürültüyü artırmadan +4 puan veren tek ayar. Gürültüyle başa çıkmak
istem v3'ün işi (alıntı zorunluluğu). Tamamı bağlamda olmayan 28 sorunun 11'inde eksik altın madde
ilk 20 adayda hiç yok (arama sorunu); 17'sinde ilk 20'de var ama reranker sıralamasında geride kalıyor
(k büyütülünce giriyor, ama gürültüyle birlikte).
