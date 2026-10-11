"""Yapılandırma yükleme.

Öncelik sırası (sonraki öncekini ezer):
  1. configs/default.yaml
  2. configs/local.yaml (varsa, Git dışında)
  3. YA_CONFIG ile verilen ek dosya (varsa)
  4. Ortam değişkenleri: YA_LLM_BASE_URL, YA_LLM_MODEL, YA_DATA_DIR
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3.5:9b"
    fallback_model: str | None = None
    temperature: float = 0.1
    seed: int | None = 42
    num_ctx: int = 8192
    think: bool = False
    max_tokens: int = 700
    timeout_s: float = 180.0
    keep_alive: int | str | None = -1  # yalnızca ollama; -1 = modeli bellekte tut

    def __post_init__(self) -> None:
        if self.backend not in ("ollama", "openai"):
            raise ValueError(f"llm.backend 'ollama' veya 'openai' olmalı, gelen: {self.backend!r}")


@dataclass(frozen=True)
class Config:
    corpus_version: str
    llm: LLMConfig
    data_dir: Path
    raw: dict[str, Any] = field(repr=False)

    def section(self, name: str) -> dict[str, Any]:
        """Henüz tiplenmemiş bölümler (embedding, retrieval...) için ham erişim."""
        return self.raw.get(name, {})


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise TypeError(f"{path} bir YAML sözlüğü içermeli")
    return data


def load_config(config_dir: Path = CONFIG_DIR, env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ) if env is None else env

    raw = _read_yaml(config_dir / "default.yaml")
    local = config_dir / "local.yaml"
    if local.exists():
        raw = _deep_merge(raw, _read_yaml(local))
    if extra := env.get("YA_CONFIG"):
        raw = _deep_merge(raw, _read_yaml(Path(extra)))

    llm_raw = dict(raw.get("llm", {}))
    if url := env.get("YA_LLM_BASE_URL"):
        llm_raw["base_url"] = url
    if model := env.get("YA_LLM_MODEL"):
        llm_raw["model"] = model

    data_dir = Path(env.get("YA_DATA_DIR") or raw.get("paths", {}).get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return Config(
        corpus_version=str(raw.get("corpus_version", "0.0.0")),
        llm=LLMConfig(**llm_raw),
        data_dir=data_dir,
        raw=raw,
    )
