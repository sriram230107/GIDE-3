"""T9: retrieval-only eval, DB-free but on REAL repo code paths.

1. Parse attention.pdf with the repo parser; take pages with >=300 chars.
2. Derive <=20 candidate Q/A pairs, each tied to its source page
   (question = first heading-like line or keyword query; expected = {source, page}).
   Saved to evidence/step4/candidate_questions.json, flagged PROVISIONAL.
3. Rank pages per question with the repo's lexical path: retrieval.search._or_query
   tokenises the question; score = fraction of query tokens present in the page text
   (mirrors the to_tsquery OR + ts_rank_cd ordering run_eval.py uses, minus Postgres).
   Fixed seed 7 for page sampling/tie-breaks.
4. Score with evaluation/metrics.py::retrieval_metrics (the same function run_eval uses).

run_eval.py itself is NOT run: it needs Postgres (AsyncSessionLocal + hybrid_search).
"""
import json
import random
import re
import sys
from pathlib import Path
from uuid import uuid4

SEED = 7
N_Q = 20

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gide" / "services" / "api"))
sys.path.insert(0, str(ROOT / "gide" / "evaluation"))

from app.ingestion.pdf_parser import extract_pdf_pages  # noqa: E402
from app.retrieval.search import _or_query  # noqa: E402
from metrics import retrieval_metrics  # noqa: E402

STOP = set("the a an and or of to in on for with is are was were be been by as at from that this these those it its into over under between which who what when where how why not no can will would should could may might must do does did done have has had having there their them they he she we you our your his her all any each few more most other some such than too very just about also".split())


def keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]{3,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda w: -freq[w])


def main() -> None:
    rng = random.Random(SEED)
    pdf = ROOT / "evidence" / "step3" / "source_files" / "attention.pdf"
    units = extract_pdf_pages(str(pdf), uuid4())
    by_page: dict[int, str] = {}
    for u in units:
        t = (u.get("content") or "").strip()
        if u.get("page_number") and len(t) >= 300:
            by_page.setdefault(u["page_number"], t)
    pages = sorted(by_page)
    rng.shuffle(pages)
    pages = sorted(pages[:N_Q])
    candidates = []
    for p in pages:
        text = by_page[p]
        kws = keywords(text)[:6]
        q = "What does the paper say about " + ", ".join(kws[:3]) + "?"
        candidates.append({"id": f"att-p{p}", "question": q, "expected_answer": text[:200],
                           "expected": {"source": "attention", "page": p}, "chunk_id": f"attention.pdf#page={p}"})
    step4 = ROOT / "evidence" / "step4"
    step4.mkdir(exist_ok=True)
    (step4 / "candidate_questions.json").write_text(
        json.dumps({"provisional": "PROVISIONAL (auto-generated, unreviewed)", "seed": SEED,
                    "items": candidates}, indent=2), encoding="utf-8")

    # Lexical ranking per question over all candidate pages.
    results, expected = [], []
    for c in candidates:
        toks = [t for t in _or_query(c["question"]).split(" | ")]
        scored = []
        for p in pages:
            low = by_page[p].lower()
            s = sum(1 for t in toks if t in low) / max(1, len(toks))
            scored.append((s, p))
        scored.sort(key=lambda x: (-x[0], rng.random()))
        cites = [{"source_title": "Attention Is All You Need (attention.pdf)", "page": p} for _, p in scored[:5]]
        results.append(cites)
        expected.append(c["expected"])
    m = retrieval_metrics(results, expected, ks=(1, 3, 5))
    out = {"seed": SEED, "n": len(candidates), "retrieval_lexical_only": m,
           "note": "PROVISIONAL: lexical-only proxy of run_eval hit@k (no DB/embeddings); run_eval.py itself BLOCKED on Postgres"}
    dest = Path(__file__).resolve().parent
    (dest / "retrieval_eval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
