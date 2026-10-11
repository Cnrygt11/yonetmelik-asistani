import json

import httpx
import pytest

from yonetmelik_asistani.config import LLMConfig
from yonetmelik_asistani.generation.llm_client import LLMClient, LLMError
from yonetmelik_asistani.generation.prompts import ContextItem, build_messages


def _client(handler, **cfg) -> LLMClient:
    return LLMClient(LLMConfig(**cfg), transport=httpx.MockTransport(handler))


def test_ollama_payload_disables_thinking_and_sets_context():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen3.5:9b", "message": {"content": "Merhaba"},
            "prompt_eval_count": 12, "eval_count": 50, "eval_duration": 2_000_000_000,
        })

    r = _client(handler).chat([{"role": "user", "content": "Selam"}])
    assert seen["path"] == "/api/chat"
    assert seen["body"]["think"] is False
    assert seen["body"]["stream"] is False
    assert seen["body"]["options"]["num_ctx"] == 8192
    assert seen["body"]["options"]["seed"] == 42
    assert seen["body"]["keep_alive"] == -1
    assert r.text == "Merhaba"
    assert r.gen_tokens_per_s == pytest.approx(25.0)


def test_openai_backend_uses_chat_completions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["max_tokens"] == 700
        return httpx.Response(200, json={
            "model": "m", "choices": [{"message": {"content": "Tamam"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        })

    r = _client(handler, backend="openai", base_url="http://x:8080").chat(
        [{"role": "user", "content": "?"}]
    )
    assert r.text == "Tamam" and r.completion_tokens == 1


def test_list_models_and_unreachable_server():
    ok = _client(lambda req: httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]}))
    assert ok.list_models() == ["qwen3.5:9b"]

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlantı reddedildi", request=request)

    with pytest.raises(LLMError):
        _client(down).list_models()


def test_build_messages_wraps_context_with_labels():
    msgs = build_messages(
        "Soru?", [ContextItem("K1", "Yönetmelik · Madde 19", "(1) metin")], duzey="lisans"
    )
    assert msgs[0]["role"] == "system" and "lisans" in msgs[0]["content"]
    assert "[K1] Yönetmelik · Madde 19\n(1) metin" in msgs[1]["content"]
    assert msgs[1]["content"].startswith("<baglam>")
