# Faz 0 · Başlangıç (1. hafta)

Plan bölüm 13'teki faz tanımı: kapsamın netleştirilmesi, depo iskeleti, Colab ve VS Code
kurulumu, Ollama ile ilk model testi.
**Çıktı:** çalışan ilk notebook ve smoke raporu.
**Çıkış ölçütü:** smoke kontrolü T4'te geçti ve aşağıdaki listenin tamamı işaretli.

## Kontrol listesi

### Depo
- [x] Dizin yapısı (plan Ek A)
- [x] `configs/default.yaml`: plandaki model ve arama ayarları
- [x] `configs/corpus_manifest.yaml`: P1 belgeler ve kaldırılmış metinler (taslak, doğrulanmadı)
- [x] `data/glossary.yaml`: öğrenci dili sözlüğü tohum listesi
- [x] LLM istemcisi (Ollama ve OpenAI uyumlu arka uç), istem şablonu, Türkçe küçük harf
- [x] Birim testleri ve kilit dosyası (`uv.lock`)
- [x] GitHub deposu oluşturuldu ve ilk commit gönderildi

### Ortam
- [x] VS Code'a Google Colab uzantısı kuruldu
- [x] `notebooks/colab_runner.ipynb` T4 üzerinde baştan sona çalıştı (11.10.2026)
- [x] Ollama `qwen3.5:9b` etiketi doğrulandı (6,6 GB, ID 56671c2ab938)
- [x] `smoke` kontrolü geçti
- [ ] Rapor (`smoke_20261011_142929.json`) Drive'dan `eval/reports/` altına eklendi
- [x] İlk ölçümler not edildi (aşağıda)

### İlk ölçümler · T4, qwen3.5:9b, 11.10.2026

| Ölçüm | Sonuç | Hedef |
|---|---|---|
| Üretim hızı | 29,5–31,7 token/sn | tahmin 20–35 |
| Soru başına süre (ısınmış model) | 4,9–10,1 sn | ≤ 20 sn (NFR-03) |
| İlk yükleme (soğuk başlangıç) | 127,6 sn | — |
| Boş bağlamda ret | doğru, birime yönlendirdi | FR-03 |
| GPU belleği (yalnız LLM) | 6.579 / 15.360 MiB | bütçe 6,6 GB |

### Gözlemler ve sonraki fazlara aktarılanlar
- **Soğuk başlangıç:** Ollama boşta kalan modeli varsayılan olarak 5 dk sonra bellekten
  çıkarıyor; sonraki soru ~2 dk bekliyor. Çözüldü: `keep_alive: -1`, kurulum sonunda modelin
  önceden yüklenmesi ve smoke'ta ayrı ısınma adımı. Faz 5'te arayüz açılışında da ısınma yapılacak.
- **Genel bilgiyle cevaplar yanlış (Faz 4 girdisi):** bağlamsız sorularda model bütünlemeyi
  "öğrencinin isteği veya ihmali" ile, yan dalı "daha derinlemesine uzmanlık" ile açıkladı;
  ikisi de yanlış. Bu, "yalnızca bağlamdan cevap" kuralının ve çıktı denetiminin zorunlu
  olduğunu doğruluyor. Bu iki soru altın sette "genel bilgi tuzağı" örneği olarak kullanılacak.
- **Türkçe akıcılık:** dil bilgisi ve akıcılık yeterli; biçimlendirmede kalın yazı ve madde
  işaretini yoğun kullanıyor (Faz 4'te istemle düzenlenecek).

### Kapanış
- [x] Plan sürüm 1.1: bireysel projeye uyarlandı (dış onaylar yerine faz kapıları, K-08)
- [ ] **Smoke raporu depoda → Faz 0 kapandı, Faz 1'e geçiş**

## Smoke raporunu okuma

| Alan | Ne anlama gelir | Beklenen |
|---|---|---|
| `gen_tokens_per_s` | Üretim hızı | T4'te 9B Q4 için yaklaşık 20–35 (tahmin; ilk ölçüm bu) |
| `wall_s` | Soru başına toplam süre | Kısa cevaplarda ≤ 20 sn |
| `<think>` uyarısı | Düşünme modu kapanmamış | Hiç görülmemeli |
| `ret_dogru` | Boş bağlamda ret cümlesi kullanıldı mı | `true` |

Ret kontrolü başarısız olursa bu Faz 0'ı engellemez, ama Faz 4'teki istem çalışmasının ilk
girdisidir; sonucu not edin. `qwen3.5:9b` etiketi yoksa veya hız hedefin çok altındaysa
aynı kontrolü `--model gemma4:e4b` ile tekrarlayın ve iki raporu karşılaştırın.
