from pathlib import Path as _P
FIXTURE = _P(__file__).parent / 'fixtures' / 'sample_textbook.pdf'
import uuid
from pathlib import Path
from app.ingestion.pdf_parser import extract_pdf_pages
from app.core.storage import get_storage_path

def test_extract_pdf_pages_real_fixture():
    fixture_path = str(FIXTURE)
    assert Path(fixture_path).exists(), "Fixture file must exist"

    source_id = uuid.uuid4()
    units = extract_pdf_pages(fixture_path, source_id)

    # Must extract units
    assert len(units) >= 4, f"Expected at least 4 units, got {len(units)}"

    # Check provenance invariants on every single extracted unit
    for u in units:
        assert u["source_id"] == source_id
        assert u["source_type"] == "pdf"
        assert u["page_number"] in [1, 2, 3]
        assert u["page_number"] > 0
        assert u["sequence_index"] is not None
        assert u["unit_metadata"] is not None

    # Check headings extracted
    headings = [u for u in units if u["unit_type"] == "heading"]
    assert len(headings) >= 1, "Must detect headings"
    assert any("CHAPTER 1" in h["content"] for h in headings)

    # Check vector diagram fallback extraction (Condition 7)
    diagrams = [u for u in units if u["unit_type"] == "diagram"]
    assert len(diagrams) >= 1, "Must extract rendered vector diagram on page 3"
    diag = diagrams[0]
    assert diag["page_number"] == 3
    assert diag["image_path"] is not None
    assert (get_storage_path() / diag["image_path"]).exists()


def test_headings_are_not_every_short_line():
    """Regression: the Step 0 heuristic marked every short single-line block as a heading."""
    units = extract_pdf_pages(str(FIXTURE), uuid.uuid4())
    body = [u for u in units if u["unit_type"] == "text"]
    assert len(body) >= 2, "paragraphs must stay 'text'"
    assert any(len(u["content"]) <= 60 for u in body), "Some short lines should remain as 'text' and not be forced to headings"
