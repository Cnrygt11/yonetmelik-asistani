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
- [ ] Cevap puanlama (otomatik ön kontrol + elle puanlama, proje sahibi örneklem kontrolü)
- [ ] Ret eşiği kalibrasyonu (sözlük bağlandıktan sonra)
- [ ] **M3**

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
