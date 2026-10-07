"""Retrieval + grounding evaluation on the team test set.

  python evaluation/run_eval.py --course-id <uuid> --testset evaluation/testset.json [--with-tutor] [--no-lexical]

Reports hit@k / MRR / citation accuracy (answerable items) and refusal precision/recall (off-material items).
--with-tutor also calls the tutor (LLM) to get its real label and cited locations, and writes the rows that
RAGAS (ragas_eval.py) consumes. Every run is saved to evaluation/results/ and the eval_runs table."""
import argparse
import asyncio
import json
from uuid import UUID

from _common import RESULTS, load_testset, save_run, save_run_db
from metrics import citation_accuracy, refusal_metrics, retrieval_metrics


async def main(a):
    from app.ai import tutor
    from app.core.database import AsyncSessionLocal
    from app.retrieval.search import citation_for, hybrid_search
    items = load_testset(a.testset)
    course = UUID(a.course_id)
    gate = tutor.load_gate()
    ans = [i for i in items if i["bucket"] == "answerable"]
    rows, ret_res, tut_cites, tut_exp, refusal_rows, ragas_rows = [], [], [], [], [], []
    async with AsyncSessionLocal() as s:
        for it in items:
            hits = await hybrid_search(s, course, it["question"], k=5, use_lexical=not a.no_lexical)
            cites = [await citation_for(s, h, n + 1) for n, h in enumerate(hits)]
            top = max((h.dense for h in hits), default=0.0)
            row = {"id": it["id"], "bucket": it["bucket"], "top_dense": round(top, 4)}
            if it["bucket"] == "answerable":
                ret_res.append(cites)
            if a.with_tutor:
                r = await tutor.answer(s, _uid(), course, it["question"])
                row.update(label=r["label"], answer=r["answer"], cited=r["citations"])
                refusal_rows.append({"expected": {"answerable": "answer", "ambiguous": "partial", "off_material": "refuse"}[it["bucket"]],
                                     "predicted_refuse": r["label"] == "NOT_COVERED"})
                if it["bucket"] == "answerable":
                    tut_cites.append(r["citations"]); tut_exp.append(it["expected"])
                    ragas_rows.append({"question": it["question"], "answer": r["answer"],
                                       "contexts": [c["snippet"] for c in r["citations"]], "ground_truth": it.get("expected_answer", "")})
            else:  # gate-only refusal (no LLM): would the retrieval gate refuse?
                refusal_rows.append({"expected": {"answerable": "answer", "ambiguous": "partial", "off_material": "refuse"}[it["bucket"]],
                                     "predicted_refuse": top < gate["dense_min"]})
            rows.append(row)
    metrics = {"retrieval": retrieval_metrics(ret_res, [i["expected"] for i in ans]),
               "refusal": refusal_metrics(refusal_rows), "gate": gate, "n_items": len(items),
               "buckets": {b: sum(1 for i in items if i["bucket"] == b) for b in ("answerable", "ambiguous", "off_material")}}
    if a.with_tutor:
        metrics["citation"] = citation_accuracy(tut_cites, tut_exp)
        (RESULTS / "last_ragas_rows.json").write_text(json.dumps(ragas_rows, indent=2))
    cfg = {"k": 5, "lexical": not a.no_lexical, "with_tutor": a.with_tutor, "testset": a.testset}
    p = save_run("rag_eval", cfg, metrics, notes=a.notes)
    (p.with_suffix(".rows.json")).write_text(json.dumps(rows, indent=2, default=str))
    await save_run_db("rag_eval", cfg, metrics, a.notes)
    print(json.dumps(metrics, indent=2)); print("saved", p)


_U = None
def _uid():
    global _U
    from uuid import uuid4
    _U = _U or uuid4()   # a throwaway user id: evaluation must not touch real learner state
    return _U


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--course-id", required=True); ap.add_argument("--testset", default="evaluation/testset.json")
    ap.add_argument("--with-tutor", action="store_true"); ap.add_argument("--no-lexical", action="store_true")
    ap.add_argument("--notes", default="")
    asyncio.run(main(ap.parse_args()))
