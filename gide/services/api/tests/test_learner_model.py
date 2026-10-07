import random
from app.learner import model as lm
from app.learner.director import plan_assessment, study_plan, target_difficulty


def test_correct_raises_incorrect_lowers():
    p = 0.4
    assert lm.update_mastery(p, True, "quiz") > p
    assert lm.update_mastery(p, False, "quiz") < p


def test_evidence_weighting_order():
    p = 0.4
    strong = lm.update_mastery(p, True, "quiz") - p
    medium = lm.update_mastery(p, True, "check") - p
    assert strong > medium > 0
    assert lm.update_mastery(p, True, "question") == p  # asking alone never moves mastery
    assert lm.update_mastery(p, None, "quiz") == p


def test_harder_items_give_more_credit_when_correct():
    easy = lm.update_mastery(0.3, True, "quiz", "mcq", 1.0)
    hard = lm.update_mastery(0.3, True, "quiz", "mcq", 5.0)
    assert hard > easy


def test_bounds():
    p = 0.5
    for _ in range(200):
        p = lm.update_mastery(p, True, "quiz")
    assert p <= 0.99
    for _ in range(200):
        p = lm.update_mastery(p, False, "quiz")
    assert p >= 0.01


def test_forgetting_monotonic():
    assert lm.retrievability(0, 5) == 1.0
    assert lm.retrievability(10, 5) < lm.retrievability(2, 5)
    assert lm.effective_mastery(0.8, 30, 2.0) < 0.8
    assert lm.effective_mastery(0.8, None, 2.0) == 0.8
    assert lm.update_stability(2.0, True, "quiz") > 2.0
    assert lm.update_stability(5.0, False, "quiz") < 5.0


def test_difficulty_update_moves_toward_data():
    assert lm.update_difficulty(3.0, 0, 0) == 3.0
    assert lm.update_difficulty(3.0, 40, 2) > 3.0   # almost everyone wrong -> harder
    assert lm.update_difficulty(3.0, 40, 38) < 3.0  # almost everyone right -> easier


def test_plan_assessment_counts_and_focus():
    cs = [{"id": "a", "eff": 0.1}, {"id": "b", "eff": 0.9}, {"id": "c", "eff": 0.5}]
    slots = plan_assessment(cs, 10, "weak", "adaptive", ["mcq", "short"], random.Random(1))
    assert len(slots) == 10
    counts = {c["id"]: sum(1 for s in slots if s["concept_id"] == c["id"]) for c in cs}
    assert counts["a"] > counts["b"]
    assert {s["qtype"] for s in slots} == {"mcq", "short"}
    bal = plan_assessment(cs, 9, "balanced", "easy", None, random.Random(1))
    assert sorted(sum(1 for s in bal if s["concept_id"] == i) for i in "abc") == [3, 3, 3]
    assert target_difficulty(0.0, "adaptive") < target_difficulty(1.0, "adaptive")


def test_study_plan_prefers_weak_prereq_and_explains():
    cs = [
        {"id": "chain", "name": "Chain Rule", "eff": 0.30, "risk": 0.5, "attempts": 3, "prereq_ids": [],
         "dependent_ids": ["bp"], "last_wrong_days": 1.0, "topic": "Calc"},
        {"id": "bp", "name": "Backprop", "eff": 0.40, "risk": 0.2, "attempts": 2, "prereq_ids": ["chain"],
         "dependent_ids": [], "last_wrong_days": 2.0, "topic": "NN"},
        {"id": "done", "name": "Mastered", "eff": 0.95, "risk": 0.05, "attempts": 9, "prereq_ids": [],
         "dependent_ids": [], "last_wrong_days": None, "topic": "X"},
    ]
    plan = study_plan(cs, 30)
    assert plan[0]["concept"] == "Chain Rule"
    assert all("Mastered" != p["concept"] for p in plan)
    assert sum(p["minutes"] for p in plan) <= 30
    assert any("Prerequisite for" in r for r in plan[0]["reasons"])
