from app.ai.tutor import decide_label, clean_citations

G = {"dense_min": 0.55, "dense_high": 0.70}


def test_label_rules():
    assert decide_label(0.40, "full", 2, G) == "NOT_COVERED"       # retrieval gate
    assert decide_label(0.80, "none", 2, G) == "NOT_COVERED"       # model says not covered
    assert decide_label(0.80, "full", 0, G) == "NOT_COVERED"       # no valid citations -> never GROUNDED
    assert decide_label(0.60, "full", 2, G) == "PARTIAL"           # weak retrieval caps the label
    assert decide_label(0.80, "partial", 1, G) == "PARTIAL"
    assert decide_label(0.80, "full", 2, G) == "GROUNDED"


def test_invalid_citation_markers_removed():
    text, used = clean_citations("A [1][3] and B [2, 9].", 3)
    assert used == [1, 2, 3] and "9" not in text
