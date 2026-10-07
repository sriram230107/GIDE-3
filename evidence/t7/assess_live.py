"""T7: live generate+verify, one per qtype, against a real parsed T5 chunk (DB-free).

Uses qwen2.5:3b (fast CPU model per .clinerules). Fixed seed not applicable to
LLM sampling here; temperature is fixed by generate.py (0.6). Times each stage;
writes evidence/t7/assess_live.json + .log. Verifier uses the same TEXT provider.
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gide" / "services" / "api"))

from app.assessment.generate import SkipQuestion, generate_question, verify_question  # noqa: E402

BANK_SRC = Path(__file__).resolve().parents[1] / "step3" / "source_files" / "attention.pdf"


def load_source() -> tuple[str, str]:
    from app.ingestion.pdf_parser import extract_pdf_pages

    units = extract_pdf_pages(str(BANK_SRC), uuid4())
    texts = [(u.get("content") or "").strip() for u in units if u.get("page_number") == 2]
    src = max(texts, key=len)
    assert len(src) >= 120, "page-2 text too short"
    return src, "attention.pdf p.2"


async def one(qtype: str, source: str) -> dict:
    t0 = time.perf_counter()
    try:
        q = await generate_question(source, qtype, 3.0, [])
    except SkipQuestion as e:
        return {"qtype": qtype, "skipped": True, "reason": str(e),
                "gen_s": round(time.perf_counter() - t0, 1)}
    gen_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    try:
        ver = await verify_question(q, source)
    except Exception as e:  # noqa: BLE001 - record provider failure, don't crash the batch
        return {"qtype": qtype, "stem": q.get("stem", "")[:200], "gen_s": round(gen_s, 1),
                "verify_error": f"{type(e).__name__}: {e}"}
    return {"qtype": qtype, "stem": q.get("stem", "")[:200], "answer": str(q.get("answer", ""))[:120],
            "gen_s": round(gen_s, 1), "verify_s": round(time.perf_counter() - t1, 1),
            "verify_ok": ver["ok"], "verify_issues": ver["issues"]}


async def main() -> None:
    src, srclabel = load_source()
    out = {"source": srclabel, "chunk_chars": len(src), "model": "qwen2.5:3b (TEXT_PROVIDER=ollama)",
           "results": [await one(t, src) for t in ("mcq", "short", "numeric")]}
    dest = Path(__file__).resolve().parent / "assess_live.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    ok = sum(1 for r in out["results"] if r.get("verify_ok"))
    print(json.dumps(out, indent=2)[:3000])
    print(f"\nVERIFY PASS RATE: {ok}/{len(out['results'])}")


if __name__ == "__main__":
    asyncio.run(main())
