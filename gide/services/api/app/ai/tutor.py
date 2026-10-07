"""Source-grounded tutor. Retrieval gate + model self-assessment + citation validation decide the label:
GROUNDED / PARTIAL / NOT_COVERED (never a made-up percentage). General-knowledge answers are labelled OUTSIDE_COURSE."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.ai import llm
from app.core.config import settings
from app.database.models import Concept, Mastery
from app.learner import model as lm
from app.retrieval.search import Hit, citation_for, hybrid_search

LEVELS = {
    "beginner": "Explain simply with an everyday analogy; avoid jargon; short steps.",
    "current": "Match the student's estimated level given below; define terms they may not know.",
    "exam": "Give an exam-ready answer: precise definitions, key formulas, the points a marker looks for.",
    "expert": "Be rigorous and concise; include derivations or edge cases when the sources support them.",
}

# Gate thresholds. DEFAULTS ARE UNCALIBRATED - run evaluation/calibrate.py to write evaluation/calibration.json.
DEFAULT_GATE = {"dense_min": 0.55, "dense_high": 0.70, "calibrated": False}


def load_gate() -> dict:
    p = Path(settings.CALIBRATION_FILE)
    if p.exists():
        try:
            g = json.loads(p.read_text())
            return {"dense_min": g["dense_min"], "dense_high": g["dense_high"], "calibrated": True,
                    "calibrated_on": g.get("calibrated_on")}
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_GATE


def decide_label(top_dense: float, model_coverage: str, n_valid_citations: int, gate: dict) -> str:
    """Pure decision rule (unit-tested)."""
    if top_dense < gate["dense_min"] or model_coverage == "none":
        return "NOT_COVERED"
    if n_valid_citations == 0:
        return "NOT_COVERED"
    if model_coverage == "partial" or top_dense < gate["dense_high"]:
        return "PARTIAL"
    return "GROUNDED"


def clean_citations(answer: str, n_sources: int) -> tuple[str, list[int]]:
    """Drop [n] markers that point at sources that do not exist; return (answer, sorted valid numbers used)."""
    used: set[int] = set()

    def sub(m):
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        ok = [x for x in nums if 1 <= x <= n_sources]
        used.update(ok)
        return "".join(f"[{x}]" for x in ok)

    return re.sub(r"\[(?:\d+\s*,?\s*)+\]", sub, answer), sorted(used)


SYSTEM = ("You are Gide, a tutor that answers ONLY from the numbered course excerpts provided. Never add facts that are not in "
          "the excerpts. Cite every claim with its excerpt number like [1] or [2]. If the excerpts only partly answer, answer "
          "the supported part and say what is missing. Output JSON only.")


async def _mastery_hint(session, user_id: UUID, concept_id: Optional[UUID]) -> str:
    if not concept_id:
        return "unknown"
    m = (await session.execute(select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id == concept_id))).scalar_one_or_none()
    if not m or m.attempts == 0:
        return "no history for this concept (treat as new)"
    return "low" if m.p_mastery < 0.4 else ("medium" if m.p_mastery < 0.7 else "high")


async def answer(session, user_id: UUID, course_id: UUID, question: str, level: str = "current",
                 mode: str = "course_only", history: Optional[list[dict]] = None) -> dict:
    gate = load_gate()
    hits: list[Hit] = await hybrid_search(session, course_id, question, k=settings.RETRIEVAL_TOP_K)
    top_dense = max((h.dense for h in hits), default=0.0)
    base = {"gate": gate, "top_dense": round(top_dense, 3), "evidence_chunks": len(hits), "level": level}
    citations = [await citation_for(session, h, i + 1) for i, h in enumerate(hits)]

    top_concept = next((h.concept_id for h in hits if h.concept_id), None)
    concept_name = None
    if top_concept:
        concept_name = (await session.execute(select(Concept.name).where(Concept.id == top_concept))).scalar_one_or_none()

    label, text, used, related, check = "NOT_COVERED", "", [], [], None
    if hits and top_dense >= gate["dense_min"]:
        ctx = "\n\n".join(f"[{i + 1}] ({c['source_title']}) {h.text}" for i, (h, c) in enumerate(zip(hits, citations)))
        hist = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in (history or [])[-6:])
        prompt = (f"Style: {LEVELS.get(level, LEVELS['current'])}\nStudent's estimated mastery of the main concept: "
                  f"{await _mastery_hint(session, user_id, top_concept)}\n\nRecent conversation:\n{hist or '(none)'}\n\n"
                  f"Course excerpts:\n{ctx}\n\nStudent question: {question}\n\nReturn JSON: "
                  '{"coverage":"full|partial|none","answer":"markdown answer with [n] citations",'
                  '"related_concepts":["names"],"check_question":"one short question to test understanding, or empty"}')
        out = await llm.agenerate_json(prompt, system=SYSTEM)
        cov = str(out.get("coverage", "none")).lower()
        text, used = clean_citations(str(out.get("answer", "")), len(hits))
        label = decide_label(top_dense, cov, len(used), gate)
        related = [str(x) for x in (out.get("related_concepts") or [])][:5]
        cq = str(out.get("check_question") or "").strip()
        if cq and top_concept and label in ("GROUNDED", "PARTIAL"):
            check = {"question": cq, "concept_id": str(top_concept), "chunk_ids": [c["chunk_id"] for c in citations if c["n"] in used][:3]}

    if label == "NOT_COVERED":
        if mode == "general":
            text = await llm.agenerate_text(
                f"Answer this student question briefly and accurately. Start by stating it is NOT from their course material.\n\n{question}")
            label, used, citations, check = "OUTSIDE_COURSE", [], [], None
        else:
            text = ("I couldn't find enough evidence in your uploaded course material to answer this. "
                    "You can ask me to answer from general knowledge (it will be clearly marked as outside your sources), "
                    "or rephrase the question.")
            used, citations = [], []

    shown = [c for c in citations if c["n"] in used] if label in ("GROUNDED", "PARTIAL") else []
    return {**base, "label": label, "answer": text, "citations": shown, "related_concepts": related,
            "primary_concept": concept_name, "primary_concept_id": str(top_concept) if top_concept else None,
            "check": check, "offer_general": label == "NOT_COVERED"}


async def judge_check(session, question: str, student_answer: str, chunk_ids: list[str]) -> dict:
    from app.database.models import Chunk
    chunks = (await session.execute(select(Chunk).where(Chunk.id.in_([UUID(x) for x in chunk_ids])))).scalars().all()
    ctx = "\n\n".join(c.text for c in chunks)
    out = await llm.agenerate_json(
        f"Source excerpts:\n{ctx}\n\nQuestion: {question}\nStudent answer: {student_answer}\n\n"
        "Judge ONLY against the excerpts. Return JSON: "
        '{"correct": true|false, "feedback":"1-2 sentences explaining what is right/missing, citing the excerpt idea"}',
        system="You are a strict but kind grader. Output JSON only.")
    return {"correct": bool(out.get("correct")), "feedback": str(out.get("feedback", ""))}
