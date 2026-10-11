# Faz 3 · Altın veri seti (plan: 3–6. haftalar)

Plan bölüm 13: soru toplama, altın madde etiketleme, alıntılı altın cevaplar, iki geçişli öz
doğrulama, setin bölünmesi. **Çıktı:** altın set v1 (150 soru).
**Çıkış ölçütü:** tüm sorular iki geçişten geçti.

## Kontrol listesi

- [ ] Derlem: 2547 **geçici md. 85** (öğrenim affı, 7592 sayılı Kanun, RG 9/8/2026). Ayrıştırıcı
      "Geçici Madde N-" biçimini, manifest geçici madde seçimini desteklemeli
- [ ] Soru kaynakları: SHMYO SSS (2025), ÖİDB duyuruları, öğrenci forumları, proje sahibinin
      çevresinden yönetmeliğe bakılmadan yazılmış sorular
- [ ] Kategoriler: mevcutlara ek olarak **norm çatışması** (kanun ile yönetmelik farklı, ör. 2547
      md. 44 / EÖY md. 15) ve **birime özgü kural** (P2 öncesi hazırlık)
- [ ] 150 soru; her birinde altın madde ve programla doğrulanan alıntı
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
