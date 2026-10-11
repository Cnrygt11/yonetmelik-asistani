# Faz 0 · Başlangıç (1. hafta)

Plan bölüm 13'teki faz tanımı: kapsamın netleştirilmesi, depo iskeleti, Colab ve VS Code
kurulumu, Ollama ile ilk model testi, paydaş görüşme talepleri.
**Çıktı:** proje tüzüğü ve çalışan ilk notebook. **Çıkış ölçütü:** danışman onayı.

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
- [ ] `notebooks/colab_runner.ipynb` T4 üzerinde baştan sona çalıştı
- [ ] Ollama `qwen3.5:9b` etiketi doğrulandı (gerekirse `configs/default.yaml` güncellendi)
- [ ] `smoke` kontrolü geçti; rapor `eval/reports/` altına eklendi
- [ ] İlk ölçümler not edildi: üretim hızı (token/sn), soru başına süre, GPU belleği

### Paydaşlar ve onay
- [ ] Proje tüzüğündeki köşeli parantezli alanlar dolduruldu
- [ ] Plan sayfası danışmanla paylaşıldı (Share menüsü)
- [ ] Görüşme talepleri gönderildi: Öğrenci İşleri, KVKK birimi, Bilgi İşlem
- [ ] **Danışman onayı alındı → Faz 1'e geçiş**

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
