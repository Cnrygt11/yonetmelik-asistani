"""LLM istemcisi (plan NFR-08: modelden bağımsız erişim).

İki arka uç desteklenir:
  * ollama : Ollama'nın yerel /api/chat uç noktası. `think` ve `num_ctx` gibi ayarlar
             yalnızca burada güvenilir biçimde uygulanabildiği için Colab varsayılanıdır.
  * openai : OpenAI uyumlu /v1/chat/completions (llama.cpp sunucusu, vLLM vb.).
Arka uç yapılandırmadan seçilir; çağıran kod değişmez.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Self

import httpx

from yonetmelik_asistani.config import LLMConfig

Message = dict[str, str]


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    wall_s: float
    gen_tokens_per_s: float | None  # yalnızca üretim hızı (Ollama bildirirse)


class LLMClient:
    def __init__(self, cfg: LLMConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.cfg = cfg
        self._http = httpx.Client(
            base_url=cfg.base_url.rstrip("/"), timeout=cfg.timeout_s, transport=transport
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- sağlık ----
    def list_models(self) -> list[str]:
        """Sunucudaki model adları. Sunucuya ulaşılamazsa LLMError."""
        try:
            if self.cfg.backend == "ollama":
                resp = self._http.get("/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
            resp = self._http.get("/v1/models")
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        except httpx.HTTPError as e:
            raise LLMError(f"LLM sunucusuna ulaşılamadı ({self.cfg.base_url}): {e}") from e

    # ---- sohbet ----
    def chat(self, messages: list[Message], *, model: str | None = None) -> ChatResult:
        model = model or self.cfg.model
        start = time.perf_counter()
        try:
            if self.cfg.backend == "ollama":
                resp = self._http.post("/api/chat", json=self._ollama_payload(messages, model))
            else:
                resp = self._http.post(
                    "/v1/chat/completions", json=self._openai_payload(messages, model)
                )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LLMError(f"LLM isteği başarısız ({e.response.status_code}): {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"LLM isteği başarısız: {e}") from e
        wall = time.perf_counter() - start
        data = resp.json()
        if self.cfg.backend == "ollama":
            return self._parse_ollama(data, model, wall)
        return self._parse_openai(data, model, wall)

    def _ollama_payload(self, messages: list[Message], model: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": self.cfg.temperature,
            "num_ctx": self.cfg.num_ctx,
            "num_predict": self.cfg.max_tokens,
        }
        if self.cfg.seed is not None:
            options["seed"] = self.cfg.seed
        return {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": self.cfg.think,
            "options": options,
        }

    def _openai_payload(self, messages: list[Message], model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        if self.cfg.seed is not None:
            payload["seed"] = self.cfg.seed
        return payload

    @staticmethod
    def _parse_ollama(data: dict[str, Any], model: str, wall: float) -> ChatResult:
        eval_count = data.get("eval_count")
        eval_ns = data.get("eval_duration")
        tps = eval_count / (eval_ns / 1e9) if eval_count and eval_ns else None
        return ChatResult(
            text=data.get("message", {}).get("content", ""),
            model=data.get("model", model),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=eval_count,
            wall_s=wall,
            gen_tokens_per_s=tps,
        )

    @staticmethod
    def _parse_openai(data: dict[str, Any], model: str, wall: float) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"Beklenmeyen yanıt: {data}")
        usage = data.get("usage") or {}
        return ChatResult(
            text=choices[0].get("message", {}).get("content", ""),
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            wall_s=wall,
            gen_tokens_per_s=None,
        )
