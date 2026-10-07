"""T10: exam_plan is pure, deterministic, reuses study_plan; weakest concepts first."""
import pytest

from app.learner.director import exam_plan, study_plan

C = [{"id": f"c{i}", "name": f"C{i}", "eff": e, "risk": 0.2, "attempts": 3,
      "prereq_ids": [], "dependent_ids": [], "last_wrong_days": None, "topic": "t"}
     for i, e in enumerate([0.2, 0.5, 0.8, 0.95])]


def test_days_span_and_minutes_capped():
    days = exam_plan(C, "2026-10-10", 30, today="2026-10-08")
    assert [d["date"] for d in days] == ["2026-10-08", "2026-10-09", "2026-10-10"]
    assert all(d["minutes"] <= 30 for d in days)


def test_weakest_first_single_day_matches_study_plan():
    days = exam_plan(C, "2026-10-08", 30, today="2026-10-08")
    assert len(days) == 1
    assert days[0]["blocks"] == study_plan(sorted(C, key=lambda c: c["eff"]), 30)
    assert days[0]["blocks"][0]["concept"] == "C0"


def test_past_exam_rejected():
    with pytest.raises(ValueError, match="in the past"):
        exam_plan(C, "2026-10-01", 30, today="2026-10-08")
