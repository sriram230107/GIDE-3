"""Question generation + verification (generate -> structural check -> independent solve -> pass/regenerate)."""
from __future__ import annotations
import random
from typing import Any, Optional

from app.ai import llm
from app.assessment.verify import check_structure, grade_numeric, numbers_close, parse_number
from app.core.config import settings

GEN_SYSTEM = ("You write exam questions for a university course. Use ONLY facts in the provided source excerpt. "
              "Never invent facts, numbers or terminology that the excerpt does not contain. Output JSON only.")


class SkipQuestion(Exception):
    pass


def _prompt(source: str, qtype: str, difficulty: float, avoid: list[str]) -> str:
    avoid_txt = "\n".join(f"- {a[:160]}" for a in avoid[:8]) or "(none)"
    common = (f"Source excerpt:\n\"\"\"\n{source[:2500]}\n\"\"\"\n\nTarget difficulty (1 easy .. 5 hard): {difficulty:.1f}\n"
              f"Do NOT repeat or paraphrase these existing questions:\n{avoid_txt}\n\n")
    if qtype == "mcq":
        return common + ('Write ONE multiple-choice question with exactly 4 options and exactly one correct option. Each WRONG option '
                         "must embody a specific, plausible misconception - state it in 'misconception' (a short sentence of the wrong belief). "
                         'Return JSON: {"stem":"","options":[{"text":"","is_correct":true,"misconception":""},...4 items],'
                         '"explanation":"why the answer is right, grounded in the excerpt","difficulty":1-5}')
    if qtype == "short":
        return common + ('Write ONE short-answer question answerable in 1-2 sentences. Return JSON: {"stem":"","answer":"model answer",'
                         '"explanation":"grounded in the excerpt","difficulty":1-5}')
    return common + ('Write ONE numerical problem that can be solved ONLY from quantities/formulas in the excerpt. If the excerpt has no '
                     'formula or quantities to compute, return {"skip": true}. Otherwise return JSON: {"stem":"","answer":"final number",'
                     '"numeric_expr":"a plain arithmetic expression using only numbers and + - * / ** ( ) sqrt log exp that computes the answer",'
                     '"tolerance":0.01,"explanation":"worked solution","difficulty":1-5}')


async def generate_question(source_text: str, qtype: str, difficulty: float, avoid: list[str]) -> dict[str, Any]:
    out = await llm.agenerate_json(_prompt(source_text, qtype, difficulty, avoid), system=GEN_SYSTEM, temperature=0.6)
    if isinstance(out, list):
        out = out[0] if out else {}
    if out.get("skip"):
        raise SkipQuestion("source has nothing to compute")
    q: dict[str, Any] = {"qtype": qtype, "stem": str(out.get("stem", "")).strip(), "explanation": str(out.get("explanation", "")).strip()}
    try:
        q["difficulty"] = float(out.get("difficulty", difficulty))
    except (TypeError, ValueError):
        q["difficulty"] = difficulty
    q["difficulty"] = max(1.0, min(5.0, q["difficulty"]))
    if qtype == "mcq":
        q["options"] = [{"text": str(o.get("text", "")).strip(), "is_correct": bool(o.get("is_correct")),
                         "misconception": str(o.get("misconception") or "").strip()} for o in (out.get("options") or [])]
        q["answer"] = next((o["text"] for o in q["options"] if o["is_correct"]), "")
    else:
        q["answer"] = str(out.get("answer", "")).strip()
        if qtype == "numeric":
            q["numeric_expr"] = str(out.get("numeric_expr") or "").strip() or None
            try:
                q["tolerance"] = float(out.get("tolerance", 0.01))
            except (TypeError, ValueError):
                q["tolerance"] = 0.01
    return q


async def verify_question(q: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Returns {ok, issues, solver}. Numeric answers are verified by CODE (safe evaluator) in check_structure,
    then cross-checked by an independent model call that sees the source and the question but NOT the key."""
    issues = check_structure(q)
    report: dict[str, Any] = {"structure_ok": not issues, "verifier_model": settings.GEMINI_VERIFIER_MODEL or settings.GEMINI_MODEL}
    if issues:
        return {"ok": False, "issues": issues, "report": report}
    model = settings.GEMINI_VERIFIER_MODEL or None
    base = (f"Source excerpt:\n\"\"\"\n{source_text[:2500]}\n\"\"\"\n\nQuestion: {q['stem']}\n")
    if q["qtype"] == "mcq":
        order = list(range(4))
        random.Random(hash(q["stem"]) & 0xFFFF).shuffle(order)
        letters = "ABCD"
        shown = "\n".join(f"{letters[i]}. {q['options'][o]['text']}" for i, o in enumerate(order))
        out = await llm.agenerate_json(
            base + f"Options:\n{shown}\n\nUsing ONLY the excerpt, solve it. Return JSON: "
            '{"answerable_from_source":true|false,"answer_letter":"A-D","reason":""}', model=model,
            system="You are an independent solver. Output JSON only.")
        report["solver"] = out
        if not out.get("answerable_from_source"):
            return {"ok": False, "issues": ["not answerable from the source excerpt"], "report": report}
        letter = str(out.get("answer_letter", "")).strip().upper()[:1]
        if letter not in letters or q["options"][order[letters.index(letter)]]["is_correct"] is not True:
            return {"ok": False, "issues": ["independent solver disagrees with the answer key"], "report": report}
        return {"ok": True, "issues": [], "report": report}
    if q["qtype"] == "numeric":
        out = await llm.agenerate_json(
            base + 'Solve it using ONLY the excerpt. Return JSON: {"answerable_from_source":true|false,"final_number":0}', model=model,
            system="You are an independent solver. Output JSON only.")
        report["solver"] = out
        if not out.get("answerable_from_source"):
            return {"ok": False, "issues": ["not answerable from the source excerpt"], "report": report}
        sv, key = parse_number(str(out.get("final_number", ""))), parse_number(q["answer"])
        if sv is None or key is None or not numbers_close(sv, key, max(q.get("tolerance") or 0.01, 0.02)):
            return {"ok": False, "issues": [f"independent solver got {sv}, key is {key}"], "report": report}
        return {"ok": True, "issues": [], "report": report}
    out = await llm.agenerate_json(
        base + "Using ONLY the excerpt, answer in 1-2 sentences. Return JSON: "
        '{"answerable_from_source":true|false,"answer":"","reason":""}', model=model,
        system="You are an independent solver. Output JSON only.")
    report["solver"] = out
    if not out.get("answerable_from_source"):
        return {"ok": False, "issues": ["not answerable from the source excerpt"], "report": report}
    j = await llm.agenerate_json(
        f"Question: {q['stem']}\nKey answer: {q['answer']}\nSolver answer: {out.get('answer', '')}\n"
        'Do these express the same answer? Return JSON: {"equivalent":true|false}', model=model,
        system="You compare answers strictly. Output JSON only.")
    report["equivalence"] = j
    if not j.get("equivalent"):
        return {"ok": False, "issues": ["independent solver disagrees with the answer key"], "report": report}
    return {"ok": True, "issues": [], "report": report}


async def grade_short(question: str, key: str, student: str, source_text: str) -> dict[str, Any]:
    out = await llm.agenerate_json(
        f"Source excerpt:\n{source_text[:2000]}\n\nQuestion: {question}\nModel answer: {key}\nStudent answer: {student}\n\n"
        'Is the student answer correct in substance (wording may differ)? Return JSON: {"correct":true|false,"feedback":"1-2 sentences"}',
        system="You are a fair grader. Output JSON only.")
    return {"correct": bool(out.get("correct")), "feedback": str(out.get("feedback", ""))}
