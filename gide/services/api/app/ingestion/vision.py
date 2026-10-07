"""Vision/OCR pass: captions + verbatim text for figures, scanned pages, slide renders and keyframes.
One OCR engine on purpose (Gemini vision); recorded per unit as metadata.ocr_engine.
The number of calls per source is capped (settings.MAX_VISION_CALLS_PER_SOURCE) and the result is reported.
"""
from __future__ import annotations
import mimetypes
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.ai import llm
from app.core.config import settings
from app.core.storage import get_source_file_path
from app.database.models import ContentUnit
from app.ingestion.video_parser import fmt_ts

PROMPT = (
    "You are indexing educational material for a student search system. Look at this image.\n"
    "Return JSON with two string fields:\n"
    '  "caption": what the image shows - type (diagram, chart, equation, code, slide, handwriting, photo), every labelled '
    "part, the relationships/arrows/flow between parts, and the key idea it teaches. Be factual; do not guess beyond what is visible.\n"
    '  "ocr_text": ALL visible text transcribed verbatim (equations in plain text). Empty string if there is none.'
)


def _compose(u: ContentUnit, caption: str, ocr: str) -> str:
    body = "; ".join(x for x in (caption.strip(), ("Text: " + ocr.strip()) if ocr.strip() else "") if x)
    if u.unit_type == "keyframe":
        return f"[On screen at {fmt_ts(u.time_start or 0)}] {body}".strip()
    if u.unit_metadata.get("is_scanned"):
        return (ocr.strip() or caption.strip() or u.content)
    if u.unit_type == "slide":
        return (u.content + "\n[Slide visual] " + body).strip()
    return body or u.content


async def run_vision(session, source_id: UUID) -> dict[str, Any]:
    stats: dict[str, Any] = {"vision_attempted": 0, "vision_done": 0, "vision_failed": 0, "vision_skipped_reason": None}
    if not llm.available():
        stats["vision_skipped_reason"] = "GEMINI_API_KEY not set"
        return stats
    res = await session.execute(
        select(ContentUnit).where(ContentUnit.source_id == source_id, ContentUnit.image_path.is_not(None),
                                  ContentUnit.vision_caption.is_(None)).order_by(ContentUnit.sequence_index))
    units = list(res.scalars().all())
    cap = settings.MAX_VISION_CALLS_PER_SOURCE
    stats["vision_candidates"] = len(units)
    if len(units) > cap:
        stats["vision_capped_at"] = cap
        units = units[:cap]
    for u in units:
        stats["vision_attempted"] += 1
        try:
            path = get_source_file_path(u.image_path)
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            out = await llm.adescribe_image(path.read_bytes(), mime, PROMPT)
            caption, ocr = str(out.get("caption", "")), str(out.get("ocr_text", ""))
            u.vision_caption, u.ocr_text = caption, ocr
            u.content = _compose(u, caption, ocr)
            u.unit_metadata = {**u.unit_metadata, "ocr_engine": f"gemini:{settings.GEMINI_MODEL}", "needs_ocr": False}
            stats["vision_done"] += 1
        except Exception as e:  # noqa: BLE001 - recorded, never hidden
            u.unit_metadata = {**u.unit_metadata, "vision_error": str(e)[:300]}
            stats["vision_failed"] += 1
    await session.flush()
    return stats
