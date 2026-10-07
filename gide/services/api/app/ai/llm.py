"""
Gide AI provider layer.

Capabilities:
- Text generation
- JSON generation
- Embeddings
- Vision
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import random
from typing import Any, Optional

import httpx
import numpy as np

from app.core.config import settings


class LLMUnavailable(RuntimeError):
    pass


# -------------------------------------------------------------------
# Provider interface (one interface, per-task provider classes)
# -------------------------------------------------------------------

class BaseProvider:
    """Single interface all providers implement. No silent fallback:
    unknown providers raise LLMUnavailable naming the provider."""

    name: str = "base"

    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        raise NotImplementedError

    def generate_json_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Return raw text; JSON parsing + repair stays in generate_json()."""
        raise NotImplementedError

    def describe_image(self, data: bytes, mime: str, prompt: str) -> str:
        """Return raw text; JSON parsing stays in describe_image()."""
        raise NotImplementedError

    def embed_texts(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        raise NotImplementedError


def _ollama_installed_models(timeout_s: float = 5.0) -> list[str]:
    """Names from Ollama /api/tags (sync, short timeout; [] on any failure)."""
    try:
        resp = httpx.get(_ollama_url("/api/tags"), timeout=timeout_s)
        if resp.status_code != 200:
            return []
        return [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        return []


def _ollama_reachable(timeout_s: float = 5.0) -> bool:
    try:
        return httpx.get(_ollama_url("/api/tags"), timeout=timeout_s).status_code == 200
    except Exception:
        return False


def _gemini_reachable(timeout_s: float = 10.0) -> bool:
    """True if a Gemini models.list() succeeds (key configured + network OK)."""
    if not settings.GEMINI_API_KEY:
        return False
    try:
        client = _get_gemini_client()
        list(client.models.list())
        return True
    except Exception:
        return False


def _capability_status(provider: str, model: str) -> dict:
    """Per-capability status: provider, model, reachable, installed.

    - ollama: reachable = daemon answers /api/tags; installed = model name present in tags.
    - gemini: reachable = models.list() succeeds; installed = True iff reachable
      (Gemini models are server-side; nothing to install locally).
    """
    provider = (provider or "").lower()
    if provider == "ollama":
        reachable = _ollama_reachable()
        tags = _ollama_installed_models() if reachable else []
        base = model.split(":")[0].lower()
        installed = any(model.lower() in t.lower() or t.lower().startswith(base + ":") for t in tags)
        return {"provider": provider, "model": model, "reachable": reachable, "installed": installed}
    if provider == "gemini":
        reachable = _gemini_reachable()
        return {"provider": provider, "model": model, "reachable": reachable, "installed": reachable}
    return {"provider": provider, "model": model, "reachable": False, "installed": False,
            "error": f"Unknown provider: {provider}"}


def available() -> bool:
    return True

def get_status() -> dict:
    text_model = settings.OLLAMA_TEXT_MODEL if settings.TEXT_PROVIDER == "ollama" else settings.GEMINI_MODEL
    embed_model = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
    vision_model = settings.OLLAMA_VISION_MODEL if settings.VISION_PROVIDER == "ollama" else settings.GEMINI_MODEL
    return {
        "text": _capability_status(settings.TEXT_PROVIDER, text_model),
        "embed": _capability_status(settings.EMBED_PROVIDER, embed_model),
        "vision": _capability_status(settings.VISION_PROVIDER, vision_model),
    }


# -------------------------------------------------------------------
# Runtime control
# -------------------------------------------------------------------

_gemini_concurrency = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
_ollama_concurrency = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)


# -------------------------------------------------------------------
# Retries
# -------------------------------------------------------------------

def _retry_sync(fn, attempts: int = 4):
    delay = 2.0

    for i in range(attempts):
        try:
            return fn()

        except LLMUnavailable:
            raise

        except Exception as e:
            msg = str(e)

            transient = any(
                token in msg
                for token in (
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "RESOURCE_EXHAUSTED",
                    "UNAVAILABLE",
                    "timed out",
                    "timeout",
                    "Too Many Requests",
                )
            )

            if i == attempts - 1 or not transient:
                raise

            # Exponential backoff + jitter
            sleep_time = delay + random.uniform(0, delay * 0.1)
            time.sleep(sleep_time)
            delay *= 2


# -------------------------------------------------------------------
# Gemini
# -------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client

    if not settings.GEMINI_API_KEY:
        raise LLMUnavailable(
            "GEMINI_API_KEY is not set in services/api/.env"
        )

    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(
            api_key=settings.GEMINI_API_KEY
        )

    return _gemini_client


# -------------------------------------------------------------------
# Ollama HTTP
# -------------------------------------------------------------------

def _ollama_url(path: str) -> str:
    return f"{settings.OLLAMA_BASE_URL.rstrip('/')}{path}"


def _ollama_generate(
    prompt: str,
    model: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.3,
) -> str:

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    if system:
        payload["system"] = system

    if json_mode:
        payload["format"] = "json"

    def call():
        try:
            response = httpx.post(
                _ollama_url("/api/generate"),
                json=payload,
                timeout=settings.LLM_TIMEOUT_S,
            )

            response.raise_for_status()
            data = response.json()
            text = data.get("response")

            if not text:
                raise LLMUnavailable(
                    f"Ollama returned no response for model {model}"
                )

            return text

        except httpx.TimeoutException as e:
            raise Exception(f"Ollama timeout: {e}")
        except httpx.HTTPError as e:
            raise Exception(f"Ollama error: {e}")

    return _retry_sync(call)


# -------------------------------------------------------------------
# JSON parsing
# -------------------------------------------------------------------

def parse_json(text: str) -> Any:
    t = (text or "").strip()

    t = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        t,
        flags=re.S,
    ).strip()

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        match = re.search(
            r"(\{.*\}|\[.*\])",
            t,
            flags=re.S,
        )

        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"model did not return valid JSON: {t[:300]!r}"
        )


# -------------------------------------------------------------------
# Public text generation
# -------------------------------------------------------------------

def generate_text(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> str:
    return get_text_provider().generate_text(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
    )


# -------------------------------------------------------------------
# Public JSON generation
# -------------------------------------------------------------------

def _generate_json_internal(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> Any:
    return get_text_provider().generate_json_text(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
    )

def generate_json(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> Any:
    # One JSON repair retry
    for attempt in range(2):
        text = _generate_json_internal(prompt, system, model, temperature)
        try:
            return parse_json(text)
        except ValueError as e:
            if attempt == 0:
                prompt += f"\n\nPrevious attempt failed: {str(e)}. Please output ONLY valid JSON."
            else:
                raise LLMUnavailable(f"Provider {settings.TEXT_PROVIDER} failed to return valid JSON after 2 attempts.") from e


# -------------------------------------------------------------------
# Explicit Gemini text generation (Keep signature)
# -------------------------------------------------------------------

def generate_gemini_text(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> str:

    from google.genai import types

    client = _get_gemini_client()

    def call():
        response = client.models.generate_content(
            model=model or settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
            ),
        )

        return response.text or ""

    return _retry_sync(call)


# -------------------------------------------------------------------
# Gemini vision
# -------------------------------------------------------------------

def describe_image(
    data: bytes,
    mime: str,
    prompt: str,
) -> Any:
    text = get_vision_provider().describe_image(data, mime, prompt)
    return parse_json(text)


# -------------------------------------------------------------------
# Embeddings
# -------------------------------------------------------------------

def embed_texts(
    texts: list[str],
    task: str = "RETRIEVAL_DOCUMENT",
) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    vectors = get_embed_provider().embed_texts(texts, task)

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# -------------------------------------------------------------------
# Provider classes (one interface: BaseProvider)
# -------------------------------------------------------------------

class OllamaProvider(BaseProvider):
    """Ollama HTTP provider (text, JSON, vision, embeddings)."""

    name = "ollama"

    def generate_text(self, prompt, system=None, model=None, temperature=0.3):
        return _ollama_generate(
            prompt=prompt,
            model=model or settings.OLLAMA_TEXT_MODEL,
            system=system,
            temperature=temperature,
        )

    def generate_json_text(self, prompt, system=None, model=None, temperature=0.2):
        return _ollama_generate(
            prompt=prompt,
            model=model or settings.OLLAMA_TEXT_MODEL,
            system=system,
            json_mode=True,
            temperature=temperature,
        )

    def describe_image(self, data, mime, prompt):
        import base64
        b64data = base64.b64encode(data).decode("utf-8")
        payload = {
            "model": settings.OLLAMA_VISION_MODEL,
            "prompt": prompt,
            "stream": False,
            "images": [b64data],
            "format": "json",
            "options": {"temperature": 0.1},
        }

        def call():
            try:
                response = httpx.post(
                    _ollama_url("/api/generate"),
                    json=payload,
                    timeout=settings.LLM_TIMEOUT_S,
                )
                response.raise_for_status()
                d = response.json()
                return d.get("response") or ""
            except Exception as e:
                raise Exception(f"Ollama vision error: {e}")

        return _retry_sync(call)

    def embed_texts(self, texts, task="RETRIEVAL_DOCUMENT"):
        payload = {
            "model": settings.OLLAMA_EMBED_MODEL,
            "input": [t[:6000] or " " for t in texts],
        }

        def call():
            try:
                response = httpx.post(
                    _ollama_url("/api/embed"),
                    json=payload,
                    timeout=settings.LLM_TIMEOUT_S,
                )
                response.raise_for_status()
                d = response.json()
                embeddings = d.get("embeddings")
                if not embeddings:
                    raise LLMUnavailable("Ollama returned no embeddings")
                return embeddings
            except Exception as e:
                raise Exception(f"Ollama embedding error: {e}")

        return _retry_sync(call)


class GeminiProvider(BaseProvider):
    """Gemini API provider (text, JSON, vision, embeddings)."""

    name = "gemini"

    def generate_text(self, prompt, system=None, model=None, temperature=0.3):
        return generate_gemini_text(
            prompt=prompt, system=system, model=model, temperature=temperature,
        )

    def generate_json_text(self, prompt, system=None, model=None, temperature=0.2):
        from google.genai import types
        client = _get_gemini_client()

        def call():
            response = client.models.generate_content(
                model=model or settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""

        return _retry_sync(call)

    def describe_image(self, data, mime, prompt):
        from google.genai import types
        client = _get_gemini_client()

        def call():
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=data, mime_type=mime),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""

        return _retry_sync(call)

    def embed_texts(self, texts, task="RETRIEVAL_DOCUMENT"):
        client = _get_gemini_client()

        def call():
            result = client.models.embed_content(
                model=settings.GEMINI_EMBED_MODEL,
                contents=texts,
            )
            return [e.values for e in result.embeddings]

        return _retry_sync(call)


def get_text_provider(name=None):
    provider = (name or settings.TEXT_PROVIDER).lower()
    if provider == "ollama":
        return OllamaProvider()
    elif provider == "gemini":
        return GeminiProvider()
    raise LLMUnavailable(f"Unknown TEXT_PROVIDER: {provider}")


def get_embed_provider(name=None):
    provider = (name or settings.EMBED_PROVIDER).lower()
    if provider == "ollama":
        return OllamaProvider()
    elif provider == "gemini":
        return GeminiProvider()
    raise LLMUnavailable(f"Unknown EMBED_PROVIDER: {provider}")


def get_vision_provider(name=None):
    provider = (name or settings.VISION_PROVIDER).lower()
    if provider == "ollama":
        return OllamaProvider()
    elif provider == "gemini":
        return GeminiProvider()
    raise LLMUnavailable(f"Unknown VISION_PROVIDER: {provider}")


# -------------------------------------------------------------------
# Model listing
# -------------------------------------------------------------------

def list_models() -> list[str]:
    # Return available gemini models + ollama models
    models = []
    try:
        if settings.GEMINI_API_KEY:
            client = _get_gemini_client()
            models.extend(m.name for m in client.models.list())
    except Exception:
        pass
        
    try:
        response = httpx.get(_ollama_url("/api/tags"), timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            models.extend(m["name"] for m in data.get("models", []))
    except Exception:
        pass
        
    return sorted(list(set(models)))


# -------------------------------------------------------------------
# Async wrappers
# -------------------------------------------------------------------

async def agenerate_text(*args, **kwargs):
    provider = settings.TEXT_PROVIDER.lower()
    sem = _ollama_concurrency if provider == "ollama" else _gemini_concurrency
    async with sem:
        return await asyncio.to_thread(generate_text, *args, **kwargs)

async def agenerate_json(*args, **kwargs):
    provider = settings.TEXT_PROVIDER.lower()
    sem = _ollama_concurrency if provider == "ollama" else _gemini_concurrency
    async with sem:
        return await asyncio.to_thread(generate_json, *args, **kwargs)

async def agenerate_gemini_text(*args, **kwargs):
    async with _gemini_concurrency:
        return await asyncio.to_thread(generate_gemini_text, *args, **kwargs)

async def agenerate_gemini_json(*args, **kwargs):
    # Backward compatibility
    async with _gemini_concurrency:
        def fn():
            from google.genai import types
            client = _get_gemini_client()
            def call():
                response = client.models.generate_content(
                    model=kwargs.get("model") or settings.GEMINI_MODEL,
                    contents=args[0] if args else kwargs.get("prompt"),
                    config=types.GenerateContentConfig(
                        system_instruction=kwargs.get("system"),
                        temperature=kwargs.get("temperature", 0.2),
                        response_mime_type="application/json",
                    ),
                )
                return response.text or ""
            return _retry_sync(call)
        
        text = await asyncio.to_thread(fn)
        return parse_json(text)

async def adescribe_image(*args, **kwargs):
    provider = settings.VISION_PROVIDER.lower()
    sem = _ollama_concurrency if provider == "ollama" else _gemini_concurrency
    async with sem:
        return await asyncio.to_thread(describe_image, *args, **kwargs)

async def aembed_texts(*args, **kwargs):
    provider = settings.EMBED_PROVIDER.lower()
    sem = _ollama_concurrency if provider == "ollama" else _gemini_concurrency
    async with sem:
        return await asyncio.to_thread(embed_texts, *args, **kwargs)