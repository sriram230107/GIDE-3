"""T4: ONE live call per capability (ollama text+embed; gemini vision). Writes evidence/t4/live_calls.log via stdout."""
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gide" / "services" / "api"))

from app.ai import llm
from app.core.config import settings

out = {}
t = time.time()
txt = llm.generate_text("Say OK")
out["text"] = {"provider": settings.TEXT_PROVIDER, "model": settings.OLLAMA_TEXT_MODEL,
               "latency_s": round(time.time() - t, 2), "reply": txt[:60]}
t = time.time()
emb = llm.embed_texts(["hello world"])
out["embed"] = {"provider": settings.EMBED_PROVIDER, "model": settings.OLLAMA_EMBED_MODEL,
                "latency_s": round(time.time() - t, 2), "dim": len(emb[0])}
t = time.time()
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
try:
    vis = llm.describe_image(png, "image/png", "What is this? Answer in 3 words.")
    out["vision"] = {"provider": settings.VISION_PROVIDER, "model": settings.GEMINI_MODEL,
                     "latency_s": round(time.time() - t, 2), "reply": vis[:120]}
except Exception as e:  # Gemini rate-limited/503 -> record, do not fake
    out["vision"] = {"provider": settings.VISION_PROVIDER, "model": settings.GEMINI_MODEL,
                     "latency_s": round(time.time() - t, 2), "error": f"{type(e).__name__}: {e}"[:200]}
print(json.dumps(out, indent=1))
