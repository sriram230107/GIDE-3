"""T5: chunk parsed PDF units with repo chunking (no DB) + cycle-rejection spot check."""
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gide" / "services" / "api"))

from app.ingestion.pdf_parser import extract_pdf_pages
from app.knowledge.chunking import chunk_units
from app.knowledge.canonical import creates_cycle

base = Path(__file__).resolve().parents[2] / "evidence" / "step3" / "source_files"
out = {}
for pdf in ["attention.pdf", "Machine_learning.pdf"]:
    units = extract_pdf_pages(str(base / pdf), uuid4())
    flat = []
    for i, u in enumerate(units):
        txt = (u.get("content") or "").strip()
        if len(txt) >= 15:
            flat.append({"id": str(uuid4()), "source_type": "pdf", "unit_type": u.get("unit_type", "text"),
                         "sequence_index": i, "page_number": u.get("page_number"),
                         "slide_number": None, "time_start": None, "time_end": None, "text": txt})
    t = time.time()
    chunks = chunk_units(flat)
    tagged = sum(1 for c in chunks if c.get("location", {}).get("page") is not None)
    span_viol = 0
    out[pdf] = {"units": len(units), "usable_units": len(flat), "chunks": len(chunks),
                "chunks_with_page": tagged, "chunk_s": round(time.time() - t, 2)}
out["cycle_check"] = {"rejects_back_edge": creates_cycle({("b", "a"), ("c", "b")}, "a", "c"),
                      "rejects_self": creates_cycle(set(), "a", "a"),
                      "allows_fresh": (not creates_cycle({("b", "a")}, "d", "a"))}
print(json.dumps(out, indent=1))
