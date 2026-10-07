"""T2: LLM layer unit tests (stub HTTP only, no live calls)."""
import asyncio
import time

import httpx
import pytest

from app.ai import llm


def _stub_response(payload):
    req = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    return httpx.Response(200, json=payload, request=req)


def _stub_response(payload):
    req = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    return httpx.Response(200, json=payload, request=req)


def test_parse_json_repair():
    # fenced block
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    # embedded in prose
    assert llm.parse_json('here: {"b": [1, 2]} done') == {"b": [1, 2]}
    # invalid raises ValueError (one repair retry happens in generate_json)
    with pytest.raises(ValueError):
        llm.parse_json("not json at all")


def test_generate_json_repair_retry(monkeypatch):
    calls = {"n": 0}

    def fake_internal(prompt, system=None, model=None, temperature=0.2):
        calls["n"] += 1
        if calls["n"] == 1:
            return "oops not json"
        return '{"ok": true}'

    monkeypatch.setattr(llm, "_generate_json_internal", fake_internal)
    assert llm.generate_json("p") == {"ok": True}
    assert calls["n"] == 2


def test_provider_interface_no_silent_fallback():
    assert isinstance(llm.get_text_provider("ollama"), llm.OllamaProvider)
    assert isinstance(llm.get_text_provider("gemini"), llm.GeminiProvider)
    assert isinstance(llm.get_embed_provider("ollama"), llm.OllamaProvider)
    assert isinstance(llm.get_vision_provider("gemini"), llm.GeminiProvider)
    with pytest.raises(llm.LLMUnavailable, match="TEXT_PROVIDER"):
        llm.get_text_provider("nope")
    with pytest.raises(llm.LLMUnavailable, match="EMBED_PROVIDER"):
        llm.get_embed_provider("nope")


def test_ollama_semaphore_limits_concurrency(monkeypatch):
    monkeypatch.setattr(llm.settings, "TEXT_PROVIDER", "ollama")
    active = {"n": 0, "peak": 0}

    def fake_generate(prompt, system=None, model=None, temperature=0.3):
        active["n"] += 1
        active["peak"] = max(active["peak"], active["n"])
        time.sleep(0.05)
        active["n"] -= 1
        return "x"

    monkeypatch.setattr(llm, "generate_text", fake_generate)
    monkeypatch.setattr(llm, "_ollama_concurrency", asyncio.Semaphore(1))

    async def run():
        await asyncio.gather(*[llm.agenerate_text("p") for _ in range(4)])

    asyncio.run(run())
    assert active["peak"] == 1


def test_retry_backoff_on_transient(monkeypatch):
    attempts = {"n": 0}
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: sleeps.append(s))

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise Exception("503 Service Unavailable")
        return "recovered"

    assert llm._retry_sync(flaky) == "recovered"
    assert attempts["n"] == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # exponential backoff


def test_retry_gives_up_and_names_provider(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def always_429():
        raise Exception("429 Too Many Requests")

    with pytest.raises(Exception, match="429"):
        llm._retry_sync(always_429, attempts=2)


def test_capability_status_stubbed(monkeypatch):
    """T4: get_status reports provider/model/reachable/installed per capability (stub HTTP only)."""
    import httpx as _httpx

    def fake_tags(url, timeout=None):
        req = _httpx.Request("GET", url)
        return _httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}, {"name": "nomic-embed-text:latest"}]}, request=req)

    monkeypatch.setattr(_httpx, "get", fake_tags)
    monkeypatch.setattr(llm.settings, "TEXT_PROVIDER", "ollama")
    monkeypatch.setattr(llm.settings, "EMBED_PROVIDER", "ollama")
    monkeypatch.setattr(llm.settings, "VISION_PROVIDER", "ollama")
    monkeypatch.setattr(llm.settings, "OLLAMA_TEXT_MODEL", "qwen2.5:3b")
    monkeypatch.setattr(llm.settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(llm.settings, "OLLAMA_VISION_MODEL", "llama3.2-vision")
    st = llm.get_status()
    for cap in ("text", "embed", "vision"):
        assert set(("provider", "model", "reachable", "installed")) <= set(st[cap])
    assert st["text"]["reachable"] is True and st["text"]["installed"] is True
    assert st["embed"]["reachable"] is True and st["embed"]["installed"] is True
    assert st["vision"]["reachable"] is True and st["vision"]["installed"] is False  # not in fake tags
    # unreachable daemon -> reachable False, installed False
    monkeypatch.setattr(_httpx, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    st2 = llm.get_status()
    assert st2["text"]["reachable"] is False and st2["text"]["installed"] is False
    # unknown provider names the problem, no silent fallback
    bad = llm._capability_status("nope", "x")
    assert bad["reachable"] is False and "Unknown provider" in bad["error"]


def test_ollama_http_stubbed(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        req = httpx.Request("POST", url)
        if url.endswith("/api/embed"):
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]}, request=req)
        return httpx.Response(200, json={"response": '{"k": 1}'}, request=req)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.OllamaProvider().generate_json_text("p") == '{"k": 1}'
    assert llm.OllamaProvider().embed_texts(["hi"]) == [[0.1, 0.2]]
