"""T12: audited answer-key error rate (pure)."""
from app.assessment.verify import audit_error_rate


def test_rate_excludes_unclear():
    r = audit_error_rate(["key_ok", "key_wrong", "key_ok", "unclear"])
    assert r == {"n_reviewed": 4, "n_decided": 3, "n_key_wrong": 1,
                 "audited_error_rate": 0.3333, "n_unclear": 1}


def test_rate_empty_and_all_unclear():
    assert audit_error_rate([])["audited_error_rate"] is None
    r = audit_error_rate(["unclear", "unclear"])
    assert r["audited_error_rate"] is None and r["n_unclear"] == 2
