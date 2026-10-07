"""PPTX ingestion: python-pptx for text/notes/tables/charts + LibreOffice (headless) for pixel-accurate slide renders.

One 'slide' ContentUnit per slide (image_path = rendered slide PNG) plus a separate speaker-notes unit.
If rendering is unavailable the slide units are still produced WITHOUT image_path and a warning is returned
(never a silent success).
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from pptx import Presentation
from pptx.util import Emu

_WIN_PATHS = [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]


def find_soffice() -> Optional[str]:
    for name in ("soffice", "soffice.exe", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in _WIN_PATHS:
        if os.path.exists(p):
            return p
    return None


def _shape_text(shape) -> list[str]:
    out: list[str] = []
    if shape.shape_type == 6 and hasattr(shape, "shapes"):  # GROUP
        for s in shape.shapes:
            out.extend(_shape_text(s))
        return out
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        t = "\n".join(p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip())
        if t:
            out.append(t)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                out.append(" | ".join(cells))
    if getattr(shape, "has_chart", False) and shape.has_chart:
        ch = shape.chart
        bits = []
        if ch.has_title and ch.chart_title.has_text_frame:
            bits.append(ch.chart_title.text_frame.text)
        try:
            bits.append("series: " + ", ".join(s.name for s in ch.plots[0].series))
            bits.append("categories: " + ", ".join(str(c) for c in ch.plots[0].categories))
        except Exception:  # noqa: BLE001
            pass
        if bits:
            out.append("[Chart] " + "; ".join(bits))
    return out


def _reading_order(shapes):
    return sorted(shapes, key=lambda s: ((s.top if s.top is not None else Emu(0)), (s.left if s.left is not None else Emu(0))))


def extract_slide_text(file_path: str) -> list[dict[str, Any]]:
    """Returns [{slide_number, title, body, notes, n_pictures}] in slide order."""
    prs = Presentation(file_path)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        title = ""
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text_frame.text.strip()
        body_parts: list[str] = []
        pics = 0
        for sh in _reading_order(slide.shapes):
            if slide.shapes.title is not None and sh.shape_id == slide.shapes.title.shape_id:
                continue
            if sh.shape_type == 13:
                pics += 1
            body_parts.extend(_shape_text(sh))
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        slides.append({"slide_number": i, "title": title, "body": "\n".join(body_parts).strip(),
                       "notes": notes, "n_pictures": pics})
    return slides


def convert_to_pdf(pptx_path: str, out_dir: str, timeout: int = 240) -> str:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice (soffice) not found; install it to render slide images")
    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")  # isolated profile avoids lock/first-run problems
    try:
        cmd = [soffice, f"-env:UserInstallation=file:///{profile_dir.replace(os.sep, '/')}", "--headless",
               "--convert-to", "pdf", "--outdir", out_dir, pptx_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        pdf = Path(out_dir) / (Path(pptx_path).stem + ".pdf")
        if res.returncode != 0 or not pdf.exists():
            raise RuntimeError(f"LibreOffice conversion failed: rc={res.returncode} {res.stderr[-400:]}")
        return str(pdf)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def render_slides(pptx_path: str, storage: Path, source_id: UUID, dpi: int = 110) -> dict[int, str]:
    """Render every slide to storage/slides/<id>/slide_<n>.png. Returns {slide_number: relative_path}."""
    import pymupdf  # imported lazily so text extraction works without it
    out_dir = storage / "slides" / str(source_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = convert_to_pdf(pptx_path, str(out_dir))
    rel: dict[int, str] = {}
    doc = pymupdf.open(pdf_path)
    try:
        for i in range(len(doc)):
            png = out_dir / f"slide_{i + 1}.png"
            doc[i].get_pixmap(dpi=dpi).save(str(png))
            rel[i + 1] = f"slides/{source_id}/slide_{i + 1}.png"
    finally:
        doc.close()
    return rel


def extract_pptx(file_path: str, source_id: UUID, storage: Optional[Path] = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Returns (unit dicts, metadata incl. warnings)."""
    slides = extract_slide_text(file_path)
    warnings: list[str] = []
    renders: dict[int, str] = {}
    if storage is not None:
        try:
            renders = render_slides(file_path, storage, source_id)
            if len(renders) != len(slides):
                warnings.append(f"render produced {len(renders)} images for {len(slides)} slides "
                                f"(hidden slides?); images mapped by order")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"slide rendering failed: {e}")

    units: list[dict[str, Any]] = []
    seq = 0
    for s in slides:
        n = s["slide_number"]
        text = (s["title"] + "\n" + s["body"]).strip() or f"[Slide {n}: no extractable text]"
        units.append({"source_id": source_id, "source_type": "pptx", "unit_type": "slide", "content": text,
                      "slide_number": n, "image_path": renders.get(n), "sequence_index": seq,
                      "unit_metadata": {"title": s["title"], "n_pictures": s["n_pictures"],
                                        "rendered": n in renders}})
        seq += 1
        if s["notes"]:
            units.append({"source_id": source_id, "source_type": "pptx", "unit_type": "text", "content": s["notes"],
                          "slide_number": n, "sequence_index": seq, "unit_metadata": {"is_speaker_note": True}})
            seq += 1
    meta = {"slide_count": len(slides), "slides_rendered": len(renders), "warnings": warnings}
    return units, meta
