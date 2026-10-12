# Faz 3 · Altın veri seti (plan: 3–6. haftalar)

Plan bölüm 13: soru toplama, altın madde etiketleme, alıntılı altın cevaplar, iki geçişli öz
doğrulama, setin bölünmesi. **Çıktı:** altın set v1 (150 soru).
**Çıkış ölçütü:** tüm sorular iki geçişten geçti.

## Kararlar

**K-12 (12.10.2026, onaylandı):** Öğrenci dili sözlüğünün aramaya bağlanması Faz 6'dan Faz 4'ün
başına alınır; ret eşiği sözlük bağlandıktan sonra kalibre edilir. Gerekçe: uçtan uca denemede
cevabı olan harç sorusunda reranker'ın ilk skoru 0,013'tü (aşağıda). Fazların sırası ve çıkış
ölçütleri değişmez. Sözlük eşleşmesi Türkçe karaktersiz yazıma dayanıklı olmalı ("harcimi").

## Soru havuzu

| Kaynak | Dosya | Soru | Not |
|---|---|---|---|
| WhatsApp, Bilgisayar Müh. 2021 ve 2022 girişli sınıf grupları | `eval/aday_sorular/whatsapp_bilgmuh_2021_2026.jsonl` | 95 | 50.490 mesajdan; anonim; derse/hocaya özgü sorular alınmadı |
| Sentetik (başka bir model), 2. sürüm | `eval/aday_sorular/sentetik_secilmis.jsonl` | 62 / 100 | Derlemde aranarak seçildi: 39 P1, 8 kısmi, 2 yanlış önkabul, 4 ret, 4 P2, 5 kapsam dışı. Uydurma sistem adları ("uluogrenci", "ulu09") UNİSİS/UKEY ile değiştirildi |

Türkçe karaktersiz yazım korunuyor: gerçek öğrenciler de böyle yazıyor. Sorun sistemde çözülür
(BM25'te ölçülen kayıp: Recall@5 0,828 → 0,793; dense Colab'da ölçülecek).
Sentetik sette bulunan yanlış önkabul örneği: BUÜ'de devamsız notu (D), "DZ" değil (EÖY md. 32/4).

Ayıklama: `scripts/whatsapp_ayikla.py` (ham dışa aktarımlar `data/private/`, Git dışı).
Belirli bir derse veya hocanın takdirine bağlı sorular altın sete alınmaz (proje sahibinin kararı).

## Kontrol listesi

- [x] Derlem v1.1 (`2026.10.2`): 2547 **geçici md. 85** (öğrenim affı, 7592 sayılı Kanun, RG
      9/8/2026). Manifest madde anahtarıyla seçiyor (`"44"`, `"G85"`); kanunlarda geçici maddeler
      "Geçici Maddeler" altında. 153 madde, 320 parça. Metinde "af" kelimesi geçmiyor: BM25
      "öğrenim affı" sorusunda bulamıyor, sözlüğe eklendi (K-12)
- [x] Türkçe karakter katlaması (BM25, F5 ve karakter n-gram): karaktersiz sorularda Recall@5
      0,793 → **0,828**, karakterli sorularda değişiklik yok (0,828 / MRR 0,603)
- [ ] Soru kaynakları: SHMYO SSS (2025), ÖİDB duyuruları, öğrenci forumları, proje sahibinin
      çevresinden yönetmeliğe bakılmadan yazılmış sorular
- [ ] Kategoriler: mevcutlara ek olarak **norm çatışması** (kanun ile yönetmelik farklı, ör. 2547
      md. 44 / EÖY md. 15) ve **birime özgü kural** (P2 öncesi hazırlık)
- [ ] 150 soru; her birinde altın madde ve programla doğrulanan alıntı
  - [x] Parti 1: wa-001..wa-048 (12.10.2026). Set 80 soru. Yeni kategoriler: `kismi` (konu
        derlemde, sorunun bir kısmı karşılıksız), `yanlis_onkabul`
  - [x] Parti 2: wa-049..wa-095 (12.10.2026). Set 127 soru; geliştirme bölümünde BM25 F5
        Recall@5 **0,655**, MRR@10 0,418
  - [ ] Parti 3: sentetik seçilmişler (sy-*)

Gerçek sorular daha zor: BM25 F5 Recall@5 ilk 32 soruda 0,828, 80 soruda **0,714**; MRR@10
0,603 → **0,459**. (Bu ölçüm bir kez test bölümünü de kapsadı; ayar yapılmadı, bundan sonra
yalnızca geliştirme bölümü.)

Etiketlemede bulunanlar:
- Koşullu geçmenin kuralı EÖY md. 35/1: GANO en az 2.00 ve FF, FD, D, K yok. Öğrencilerin en sık
  sorduğu konulardan.
- **Yaz Öğretimi Yönetmeliği md. 7/1 ve 13/1, yürürlükten kalkmış 2014 tarihli (RG 29098)
  Öğretim Yönetmeliği'ne atıf yapıyor.** Model öğrenciye kaldırılmış yönetmeliği gösterebilir;
  istem ve denetim bunu ele almalı. YDYO md. 24/2 de eski adı ("Uludağ Üniversitesi Önlisans ve
  Lisans Öğretim Yönetmeliği") kullanıyor.
- YDYO md. 7'nin (4). fıkrası (muafiyet harf notu tablosu) ve md. 7/3-b'nin andığı eşdeğer sınav
  tabloları resmî metinde md. 8/4'ten sonra basılmış (mevzuat.gov.tr ve KAYSİS aynı). Çıkarma
  hatası değil; bu konudaki sorularda md. 7 ve md. 8 birlikte altın kabul edilir. Faz 2'deki
  "md. 8'de iki (4) numaralı fıkra" notunun açıklaması budur.
- **EÖY md. 20 disiplin işlerini yürürlükten kalkmış 2012 tarihli Öğrenci Disiplin
  Yönetmeliği'ne bağlıyor** (kaldırıldı: RG 32129, 2023). Disiplin hükümleri 2547 md. 54'te.
  Kopya sorularında model bu atfa güvenmemeli.
- "Yaz okulunda staj" sorusu P2 sanılmıştı; cevap Yaz Öğr. Yön. md. 10/1-i'de.
- Sentetik sy-016 ("harf notları kaç gün içinde") yanlışlıkla "derlemde yok" etiketlenmişti:
  EÖY md. 29/11 "en geç 3 gün içinde ilân edilir".
- [ ] İkinci geçiş (proje sahibi): başlangıçtaki 32 soru dahil
- [ ] Bölünme: mevcut kalıcı kural (%30 test)

## Faz 4 için ön bulgular · uçtan uca deneme · 12.10.2026 · Colab T4

`eval/e2e_deneme.py`, Qwen3.5-9B Q4_K_M + BGE-M3 + reranker aynı T4'te. GPU **9,4 / 15,4 GB**;
ısınma 53 sn; cevap başına 6–20 sn. Altı sorunun tamamında kaynak etiketleri geçerli.

| Soru | Sonuç | Neden |
|---|---|---|
| Kayıt dondurma süresi | **Doğru**: iki süre de ayrı ayrı verildi | md. 19 bütün olarak bağlamda |
| Tek ders sınavı | **Yanlış**: "tek ders = bütünleme" dedi | md. 31 (ek sınav) bulunamadı; model eşdeğerliği kendi bilgisinden kurdu |
| Harç ödememe | İçerik doğru, sonuna ret cümlesi eklendi | Karma cevap; denetim bunu "ret" saydı |
| Azami süre, son sınıf | **Kısmen yanlış**: ilk cümle "ek sınav verilmez" | md. 44'teki ara sınıf/son sınıf ayrımı ilk cümlede kayboldu; 7592'nin "iki ek sınav" hakkı atlandı |
| Öğrenim affı | Doğru ret | Geçici md. 85 derlemde yok (beklenen) |
| Yurt ücreti | Doğru ret | Derlem dışı |

Çıkarımlar:
1. **Sözlük erken gerekli.** "Tek ders" ve "harç/atılmak" sorularında reranker'ın ilk skoru 0,31 ve
   0,013. Reranker skoruna dayalı bir ret eşiği, cevabı olan harç sorusunu reddederdi. Öğrenci dili
   sözlüğü (plan: Faz 6) ret eşiği kalibrasyonundan (Faz 4) önce bağlanmalı. Önerilen karar: K-12.
2. **İstem:** ret cümlesi yalnızca hiç cevap yokken; terim eşdeğerliği yalnızca bağlamdan; ilk
   cümle istisnaları da taşımalı (ör. "ara sınıf öğrencilerine verilmez, son sınıfa iki hak").
3. **Denetim:** ret cümlesi ve kaynak etiketi birlikteyse "karma" olarak işaretlenmeli.
4. **Bağlam:** reranker skoru çok düşük kaynaklar (kayıt dondurmada 5 ilgisiz kaynak) atılmalı;
   eşik göreli olmalı (ilk skora oranla), çünkü harç sorusunda bütün skorlar düşük.
5. **Norm hiyerarşisi:** 7592 ile değişen kanun hükmü ile henüz güncellenmemiş yönetmelik
   hükmü aynı bağlamda. Başlıkta belge türü ve son değişiklik tarihi açıkça yazılmalı; istem
   kural 6 bu durumu kapsamalı.
