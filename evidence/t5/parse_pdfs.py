"""T5: parse staged PDFs with the repo parser (no DB). Writes evidence/t5/pdf_parse.log via stdout."""
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gide" / "services" / "api"))

from app.ingestion.pdf_parser import extract_pdf_pages

base = Path(__file__).resolve().parents[2] / "evidence" / "step3" / "source_files"
out = {}
for pdf in ["attention.pdf", "Machine_learning.pdf"]:
    t = time.time()
    units = extract_pdf_pages(str(base / pdf), uuid4())
    texts = [u.get("content", "") or "" for u in units]
    chars = sum(len(x) for x in texts)
    out[pdf] = {"units": len(units), "total_chars": chars, "parse_s": round(time.time() - t, 2),
                "sample_head": (texts[0] if texts else "")[:120]}
print(json.dumps(out, indent=1))
