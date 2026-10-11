#!/usr/bin/env bash
# Colab'da Ollama'yı kurar, başlatır ve modeli indirir (plan 12.2, adım 4).
# Kullanım: bash scripts/colab_setup.sh [model]   (varsayılan: qwen3.5:9b)
set -euo pipefail

MODEL="${1:-qwen3.5:9b}"
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-8192}"
# Varsayılan 5 dk; boşta kalan model bellekten çıkar ve sonraki soru ~2 dk bekler.
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
# OLLAMA_MODELS ayarlıysa (ör. Drive) modeller oraya yazılır; değilse yerel diske.
[[ -n "${OLLAMA_MODELS:-}" ]] && mkdir -p "$OLLAMA_MODELS" && export OLLAMA_MODELS

if ! command -v ollama >/dev/null 2>&1; then
  echo ">> Ollama kuruluyor"
  apt-get -qq update >/dev/null
  apt-get -qq install -y pciutils lshw zstd >/dev/null   # GPU algılama ve arşiv açma için
  curl -fsSL https://ollama.com/install.sh | sh
fi

if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo ">> Ollama sunucusu başlatılıyor (log: /content/ollama.log)"
  setsid nohup ollama serve >/content/ollama.log 2>&1 &
  for _ in $(seq 1 60); do
    curl -sf http://localhost:11434/api/tags >/dev/null && break
    sleep 1
  done
fi
curl -sf http://localhost:11434/api/tags >/dev/null \
  || { echo "HATA: Ollama başlatılamadı; /content/ollama.log dosyasına bakın" >&2; exit 1; }

echo ">> Model indiriliyor: $MODEL"
ollama pull "$MODEL"

echo ">> Model GPU'ya yükleniyor (ilk yükleme 1-2 dk sürebilir)"
curl -sf http://localhost:11434/api/generate \
  -d "{\"model\": \"$MODEL\", \"prompt\": \"\", \"keep_alive\": -1}" >/dev/null
ollama ps
