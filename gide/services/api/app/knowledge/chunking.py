"""Pure chunking: ContentUnit dicts -> retrieval chunks that keep exact provenance.

Each chunk records the ids of every unit it was built from and a primary unit (the first one),
whose page/slide/timestamp is what a citation opens. Chunks never span pages (pdf) or slides (pptx).
"""
from __future__ import annotations
from typing import Any

MAX_CHARS = 900
MIN_CHARS = 200
VIDEO_WINDOW_S = 60.0
MIN_TEXT = 15
VISUAL_TYPES = {"diagram", "keyframe", "image"}


def search_text(content: str | None, caption: str | None, ocr: str | None) -> str:
    """Text used for embedding/search. Placeholder content like '[Figure on Page 3 ...]' is dropped when a caption exists."""
    parts: list[str] = []
    c = (content or "").strip()
    if c and not (c.startswith("[") and c.endswith("]") and (caption or ocr)):
        parts.append(c)
    for extra in (caption, ocr):
        e = (extra or "").strip()
        if e and e not in parts and e not in c:
            parts.append(e)
    return "\n".join(parts).strip()


def _loc(u: dict[str, Any]) -> dict[str, Any]:
    return {"page": u.get("page_number"), "slide": u.get("slide_number"),
            "time_start": u.get("time_start"), "time_end": u.get("time_end")}


def _mk(units: list[dict[str, Any]], text: str) -> dict[str, Any]:
    first = units[0]
    loc = _loc(first)
    if first.get("time_start") is not None:
        ends = [u["time_end"] for u in units if u.get("time_end") is not None]
        if ends:
            loc["time_end"] = max(ends)
    return {"text": text, "unit_ids": [u["id"] for u in units], "primary_unit_id": first["id"], "location": loc}


def chunk_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """units: dicts with id, source_type, unit_type, sequence_index, page_number, slide_number,
    time_start, time_end, text (already composed with search_text)."""
    if not units:
        return []
    st = units[0]["source_type"]
    units = sorted(units, key=lambda u: (u["sequence_index"],))
    if st == "pdf":
        return _chunk_pdf(units)
    if st == "pptx":
        return _chunk_slides(units)
    if st == "video":
        return _chunk_video(units)
    return [_mk([u], u["text"]) for u in units if len(u["text"]) >= MIN_TEXT]


def _chunk_pdf(units):
    chunks, cur, cur_len, cur_page = [], [], 0, None

    def flush():
        nonlocal cur, cur_len
        if cur:
            chunks.append(_mk(cur, "\n".join(u["text"] for u in cur)))
        cur, cur_len = [], 0

    for u in units:
        t = u["text"]
        if len(t) < MIN_TEXT and u["unit_type"] not in VISUAL_TYPES:
            continue
        if not t:
            continue
        if u["unit_type"] in VISUAL_TYPES:  # figures are standalone so a citation opens the figure itself
            flush()
            chunks.append(_mk([u], t))
            continue
        if cur_page is not None and u["page_number"] != cur_page:
            flush()
        cur_page = u["page_number"]
        if u["unit_type"] == "heading" and cur_len >= MIN_CHARS:
            flush()
        if cur and cur_len + len(t) > MAX_CHARS:
            flush()
        cur.append(u)
        cur_len += len(t) + 1
    flush()
    return chunks


def _chunk_slides(units):
    by_slide: dict[int, list] = {}
    for u in units:
        by_slide.setdefault(u["slide_number"], []).append(u)
    chunks = []
    for s in sorted(by_slide):
        us = by_slide[s]
        # slide unit first so the primary unit is the rendered slide
        us.sort(key=lambda u: (u["unit_type"] != "slide", u["sequence_index"]))
        text = "\n".join(u["text"] for u in us if u["text"])
        if len(text) >= MIN_TEXT:
            chunks.append(_mk(us, text))
    return chunks


def _chunk_video(units):
    caps = [u for u in units if u["unit_type"] == "caption" and u["text"]]
    keys = [u for u in units if u["unit_type"] == "keyframe" and u["text"]]
    if not caps and not keys:
        return []
    horizon = max([u["time_end"] for u in units if u.get("time_end") is not None] or [0.0])
    chunks, t0 = [], 0.0
    while t0 <= horizon:
        t1 = t0 + VIDEO_WINDOW_S
        win_caps = [u for u in caps if t0 <= u["time_start"] < t1]
        win_keys = [u for u in keys if t0 <= u["time_start"] < t1]
        members = win_caps + win_keys
        if members:
            members.sort(key=lambda u: u["time_start"])
            primary = win_caps[0] if win_caps else win_keys[0]
            ordered = [primary] + [u for u in members if u is not primary]
            text = " ".join(u["text"] for u in win_caps)
            if win_keys:
                text += "\n[On screen] " + " | ".join(u["text"] for u in win_keys)
            c = _mk(ordered, text.strip())
            c["location"]["time_start"] = primary["time_start"]
            chunks.append(c)
        t0 = t1
    return [c for c in chunks if len(c["text"]) >= MIN_TEXT]
