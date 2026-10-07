import numpy as np
from app.assessment.verify import (safe_eval, check_structure, grade_numeric, grade_mcq, is_duplicate, stem_hash,
                                   parse_number, numbers_close)


def test_safe_eval_blocks_code():
    assert safe_eval("2 * (3 + 4) ** 2") == 98.0
    assert abs(safe_eval("sqrt(16) + pi") - (4 + 3.141592653589793)) < 1e-9
    for bad in ["__import__('os').system('x')", "open('f')", "a + 1", "[1,2]", "(1).__class__", "2**1000"]:
        try:
            safe_eval(bad)
        except Exception:
            continue
        raise AssertionError(f"should have rejected {bad!r}")


def mcq(correct_idx=0, miscon=True, n=4):
    opts = [{"text": f"opt{i}", "is_correct": i == correct_idx, "misconception": ("m" if miscon else "")} for i in range(n)]
    return {"qtype": "mcq", "stem": "What?", "explanation": "because", "options": opts, "answer": "opt0"}


def test_structure_checks():
    assert check_structure(mcq()) == []
    assert any("exactly 4" in i for i in check_structure(mcq(n=3)))
    assert any("misconception" in i for i in check_structure(mcq(miscon=False)))
    q = mcq(); q["options"][1]["is_correct"] = True
    assert any("exactly one" in i for i in check_structure(q))
    num = {"qtype": "numeric", "stem": "Compute", "explanation": "e", "answer": "98", "numeric_expr": "2*(3+4)**2", "tolerance": 0.01}
    assert check_structure(num) == []
    num["answer"] = "99"
    assert any("evaluates to" in i for i in check_structure(num))
    num.pop("numeric_expr")
    assert any("needs numeric_expr" in i for i in check_structure(num))


def test_numeric_grading():
    assert grade_numeric("about 98.0 units", "98", 0.01)
    assert grade_numeric("1,000", "1000", 0.001)
    assert not grade_numeric("97", "98", 0.001)
    assert not grade_numeric("none", "98", 0.01)
    assert parse_number("-3.5e2") == -350.0
    assert numbers_close(0.0, 0.0, 0.01)


def test_mcq_grading_respects_shuffle():
    opts = mcq()["options"]
    order = [2, 0, 3, 1]  # shown order -> original index; original 0 (correct) is shown at position 1
    assert grade_mcq(opts, order, 1) == (True, None)
    ok, mis = grade_mcq(opts, order, 0)
    assert ok is False and mis == "m"


def test_duplicates():
    h = {stem_hash("What is the learning rate?")}
    assert is_duplicate("what is  the learning rate", None, h, None)[0]
    known = np.array([[1.0, 0.0]])
    assert is_duplicate("different", np.array([0.99, 0.141]) / np.linalg.norm([0.99, 0.141]), set(), known)[0]
    assert not is_duplicate("different", np.array([0.0, 1.0]), set(), known)[0]
