# Multimodal Ingestion Pipeline

**Project:** Gide, Source-Grounded Adaptive Tutor  
**Phase:** 1 (Ingestion + Provenance + Source Viewing)

---

## 1. Provenance Guarantee

Every content unit extracted by Gide preserves its exact origin down to:
- `source_id`: Canonical foreign key reference to the parent source.
- `source_type`: One of `pdf`, `pptx`, `video`, or `image`.
- `page_number`: 1-indexed page in PDF textbook.
- `slide_number`: 1-indexed slide in PPTX presentation.
- `time_start` & `time_end`: Exact seconds interval $[t_{start}, t_{end}]$ for video caption and keyframe units.
- `bounding_box`: Normalized $[0.0, 1.0]$ coordinates $\{x_0, y_0, x_1, y_1\}$.
- `image_path`: Relative path to extracted diagram crop, rendered slide, or keyframe.

Downstream systems (retrieval in Phase 2, tutor grounding in Phase 3, adaptive assessments in Phase 4) reference **exclusively** this `ContentUnit` model. Ad-hoc citation strings are strictly disallowed.

---

## 2. Textbooks & Document Ingestion (PDF)

### 2.1 Engine
`PyMuPDF` (`pymupdf` v1.28.2).

### 2.2 Extraction Algorithm
1. Open document with `pymupdf.open(file_path)`.
2. Iterate through each page ($p = 1 \dots N$).
3. Extract structured text blocks via `page.get_text("blocks")`.
4. Normalize bounding box coordinates against page dimensions ($width, height$).
5. Classify text blocks into `heading` vs `text` using length and capitalization heuristics.
6. Figure Extraction & Fallback (Condition 7):
   - **Embedded Raster Images:** Extracted using `page.get_images()`. Filtered for icons/thumbnails ($<80\times 80\text{px}$). Valid figures are saved to `storage/images/{source_id}/page_{p}_img_{i}.{ext}` as `unit_type="diagram"`.
   - **Vector Diagrams Fallback:** For diagrams constructed purely using vector curves, paths, and shapes (without embedded raster objects), `page.get_drawings()` detects the vector path cluster and renders the page crop via `page.get_pixmap(dpi=150)` to `storage/images/{source_id}/page_{p}_vector_render.png`.

---

## 3. Asynchronous Worker Architecture

- **Task Queue:** `arq` (async Redis queue) on `127.0.0.1:6379`.
- **Worker Process:** Runs natively on Windows via `python -m arq app.worker.WorkerSettings` using Python's native `asyncio` loop, resolving the Unix `os.fork()` limitation of RQ.
- **Job States:**
  - `queued` $\rightarrow$ `processing` (stage: `extracting_pages`) $\rightarrow$ `storing_units` $\rightarrow$ `completed`.
- **Failure Transparency:**
  - Any parsing or database exception immediately rolls back the transaction.
  - Updates `ProcessingJob` state to `failed` and saves the complete Python traceback in `error_detail`.
  - Updates `Source` status to `failed` and sets `error_message`.
  - The UI transparently surfaces this error message without simulation.

---

## 4. Known Issues & Limitations (Step 0)
1. **Scanned PDF Pages:** Pages lacking native text layers currently yield empty text blocks until OCR (Step 2) is connected.
2. **Multi-Column Flow:** Complex multi-column newspaper layouts are currently linearized based on vertical reading order.
3. **Password-Protected PDFs:** PDFs with owner/user passwords will reject upload with an explicit error message.
