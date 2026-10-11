# Yönetmelik Asistanı

Bursa Uludağ Üniversitesi öğrencilerinin yönetmelik ve yönergelerle ilgili sorularını,
yürürlükteki metne atıf yaparak cevaplayan, yalnızca açık kaynaklı modellerle çalışan
bir soru-cevap (RAG) sistemi.

> Bu proje Bursa Uludağ Üniversitesi'nin resmî bir hizmeti değildir.

- **Proje planı (v1.1):** https://claude.ai/artifact/U8QJsVHXf3HtWBYQzY1Xau
- **Çalışma biçimi:** bireysel proje; her faz `docs/FAZ_n.md` içindeki çıkış ölçütleriyle kapanır
- **Güncel faz:** Faz 1 · Derlem (Faz 0 tamamlandı: [rapor](docs/FAZ_0.md))

## Mimari özeti

| Bileşen | Seçim |
|---|---|
| Cevap modeli | Qwen3.5-9B (Q4, Ollama) · yedek Gemma 4 E4B |
| Arama | BM25 (Türkçe kök) + BGE-M3, RRF, bge-reranker-v2-m3 |
| Vektör DB | Qdrant |
| Arayüz | Gradio (Faz 5) |
| Geliştirme ortamı | VS Code + Google Colab uzantısı, NVIDIA T4 |

## Yerel geliştirme

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Yerel ayarlar için `configs/local.yaml` oluşturun (Git dışında); yalnızca değiştirmek
istediğiniz anahtarları yazmanız yeterli. Ortam değişkenleri: `YA_LLM_BASE_URL`,
`YA_LLM_MODEL`, `YA_DATA_DIR`, `YA_CONFIG`.

## Colab'da çalıştırma

1. VS Code'da Google'ın resmî **Google Colab** uzantısını kurun.
2. [notebooks/colab_runner.ipynb](notebooks/colab_runner.ipynb) dosyasını açın, çekirdek
   olarak Colab'ı ve **T4 GPU** çalışma zamanını seçin.
3. Hücreleri sırayla çalıştırın. Depo özelse Colab *Secrets* bölümüne `GITHUB_TOKEN` ekleyin.

Depo: https://github.com/Cnrygt11/yonetmelik-asistani

Son hücre `python -m yonetmelik_asistani.smoke` sağlık kontrolünü çalıştırır: GPU, Ollama,
Türkçe akıcılık, hız ve boş bağlamda ret davranışı.

## Dizin yapısı

```
configs/            default.yaml (ayarlar) · corpus_manifest.yaml (belge envanteri)
data/               raw/ ve processed/ Git dışında · glossary.yaml (öğrenci dili sözlüğü)
docs/               faz kontrol listeleri (FAZ_n.md)
eval/               altın set ve değerlendirme raporları
notebooks/          Colab çalıştırıcı
scripts/            Colab kurulum betiği
src/yonetmelik_asistani/
  ingest/ chunking/ index/ retrieval/ generation/ api/ ui/
tests/
```
