import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from metrics import location_matches, retrieval_metrics, refusal_metrics, citation_accuracy, best_threshold


def test_location_matching():
    c = {"source_title": "ML Textbook.pdf", "page": 3}
    assert location_matches({"source": "textbook", "page": 3}, c)
    assert not location_matches({"source": "textbook", "page": 4}, c)
    assert not location_matches({"source": "slides", "page": 3}, c)
    v = {"source_title": "Lecture 5", "time_start": 100.0, "time_end": 130.0}
    assert location_matches({"source": "lecture 5", "t_start": 128, "t_end": 140}, v)
    assert location_matches({"source": "lecture 5", "t_start": 134, "t_end": 140}, v)      # within 5 s tolerance
    assert not location_matches({"source": "lecture 5", "t_start": 200, "t_end": 210}, v)
    assert location_matches({"slide": 8}, {"slide": 8, "source_title": "x"})


def test_retrieval_metrics():
    exp = [{"page": 1}, {"page": 2}]
    res = [[{"page": 9}, {"page": 1}], [{"page": 2}]]
    m = retrieval_metrics(res, exp)
    assert m["hit@1"] == 0.5 and m["hit@3"] == 1.0 and m["mrr"] == 0.75


def test_refusal_metrics():
    rows = [{"expected": "refuse", "predicted_refuse": True}, {"expected": "refuse", "predicted_refuse": False},
            {"expected": "answer", "predicted_refuse": True}, {"expected": "answer", "predicted_refuse": False}]
    m = refusal_metrics(rows)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["answerable_over_refusal_rate"] == 0.5


def test_citation_accuracy_and_threshold():
    assert citation_accuracy([[{"page": 1}], []], [{"page": 1}, {"page": 2}])["citation_accuracy"] == 1.0
    b = best_threshold([0.8, 0.7, 0.65], [0.4, 0.5, 0.52])
    assert 0.65 <= b["threshold"] <= 0.7 and b["f1"] == 1.0 and best_threshold([], [1]) is None
