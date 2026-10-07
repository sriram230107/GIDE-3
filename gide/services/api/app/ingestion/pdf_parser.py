import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import pymupdf

from app.core.storage import get_storage_path

MIN_DRAWINGS_FOR_FIGURE = 1      # page rules/underlines alone should not count as a figure
SCANNED_MIN_CHARS = 50           # fewer text chars than this on a page with graphics => treat as scanned
SCANNED_PLACEHOLDER = "[Scanned page: OCR pending]"


def _block_styles(page) -> Dict[int, Tuple[float, bool]]:
    """block number -> (max font size, bold?) using PyMuPDF's 'dict' extraction."""
    styles: Dict[int, Tuple[float, bool]] = {}
    try:
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") != 0:
                continue
            size, bold = 0.0, False
            for line in b.get("lines", []):
                for sp in line.get("spans", []):
                    if sp.get("text", "").strip():
                        size = max(size, float(sp.get("size", 0.0)))
                        bold = bold or bool(sp.get("flags", 0) & 16) or "bold" in sp.get("font", "").lower()
            styles[b.get("number", -1)] = (size, bold)
    except Exception:  # noqa: BLE001  (style info is a heuristic aid only)
        pass
    return styles


def _body_font_size(doc) -> float:
    """Most common font size by character count across the document = body text size."""
    counts: Counter = Counter()
    for page in doc:
        try:
            for b in page.get_text("dict").get("blocks", []):
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for sp in line.get("spans", []):
                        counts[round(float(sp.get("size", 0.0)), 1)] += len(sp.get("text", ""))
        except Exception:  # noqa: BLE001
            continue
    return counts.most_common(1)[0][0] if counts else 11.0


def _is_heading(text: str, size: float, bold: bool, body: float) -> bool:
    if len(text) >= 150 or text.count("\n") > 1:
        return False
    if text.isupper() and len(text) >= 3:
        return True
    if size and size >= body * 1.15:
        return True
    if bold and len(text) < 100 and not text.rstrip().endswith("."):
        return True
    return bool(re.match(r"^(chapter|section|unit|lecture)\s+\d", text, re.I))


def extract_pdf_pages(file_path: str, source_id: UUID) -> List[Dict[str, Any]]:
    """Structured ContentUnits from a PDF. Every unit has a 1-indexed page_number, sequence index and
    (for text) a normalised bounding box. Figures are saved as images for the vision pass; scanned pages are
    rendered and flagged for OCR."""
    doc = pymupdf.open(file_path)
    storage = get_storage_path()
    (storage / "images" / str(source_id)).mkdir(parents=True, exist_ok=True)
    body_size = _body_font_size(doc)

    units: List[Dict[str, Any]] = []
    seq = 0

    def add(**kw):
        nonlocal seq
        base = {"source_id": source_id, "source_type": "pdf", "slide_number": None, "time_start": None,
                "time_end": None, "image_path": None, "bounding_box": None, "sequence_index": seq}
        base.update(kw)
        units.append(base)
        seq += 1

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]
        pw, ph = page.rect.width or 1.0, page.rect.height or 1.0
        styles = _block_styles(page)
        blocks = page.get_text("blocks")
        page_chars = 0
        text_blocks = []
        for b in blocks:
            x0, y0, x1, y1, text, block_no, b_type = b[:7]
            clean = text.strip() if b_type == 0 else ""
            if clean:
                page_chars += len(clean)
                text_blocks.append((x0, y0, x1, y1, clean, block_no))

        images = page.get_images(full=True)
        drawings = page.get_drawings()
        is_scanned = page_chars < SCANNED_MIN_CHARS and (bool(images) or len(drawings) >= MIN_DRAWINGS_FOR_FIGURE)

        for x0, y0, x1, y1, clean, block_no in text_blocks:
            size, bold = styles.get(block_no, (0.0, False))
            add(unit_type="heading" if _is_heading(clean, size, bold, body_size) else "text",
                content=clean, page_number=page_num,
                bounding_box={"x0": round(x0 / pw, 4), "y0": round(y0 / ph, 4),
                              "x1": round(x1 / pw, 4), "y1": round(y1 / ph, 4)},
                unit_metadata={"block_no": block_no, "char_count": len(clean), "page": page_num,
                               "font_size": round(size, 1), "bold": bold})

        if is_scanned:
            rel = f"images/{source_id}/page_{page_num}_scan.png"
            page.get_pixmap(dpi=150).save(str(storage / rel))
            add(unit_type="text", content=SCANNED_PLACEHOLDER, page_number=page_num, image_path=rel,
                bounding_box={"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
                unit_metadata={"is_scanned": True, "needs_ocr": True, "page": page_num})
            continue

        if images:
            for img_idx, img_info in enumerate(images):
                xref = img_info[0]
                base_img = doc.extract_image(xref)
                if not base_img or base_img["width"] < 80 or base_img["height"] < 80:
                    continue
                ext = base_img["ext"]
                rel = f"images/{source_id}/page_{page_num}_img_{img_idx}.{ext}"
                with open(storage / rel, "wb") as f:
                    f.write(base_img["image"])
                bbox = None
                try:
                    r = page.get_image_rects(xref)
                    if r:
                        bbox = {"x0": round(r[0].x0 / pw, 4), "y0": round(r[0].y0 / ph, 4),
                                "x1": round(r[0].x1 / pw, 4), "y1": round(r[0].y1 / ph, 4)}
                except Exception:  # noqa: BLE001
                    pass
                add(unit_type="diagram", content=f"[Figure on Page {page_num}: {base_img['width']}x{base_img['height']}]",
                    page_number=page_num, image_path=rel, bounding_box=bbox,
                    unit_metadata={"format": ext, "width": base_img["width"], "height": base_img["height"], "is_diagram": True})
        elif len(drawings) >= MIN_DRAWINGS_FOR_FIGURE:
            # Vector diagrams have no embedded image: render the page as the documented fallback.
            rel = f"images/{source_id}/page_{page_num}_vector_render.png"
            page.get_pixmap(dpi=150).save(str(storage / rel))
            add(unit_type="diagram", content=f"[Rendered Vector Diagram on Page {page_num}]", page_number=page_num,
                image_path=rel, bounding_box={"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
                unit_metadata={"is_vector_diagram_render": True, "drawing_paths_count": len(drawings)})

    doc.close()
    return units
