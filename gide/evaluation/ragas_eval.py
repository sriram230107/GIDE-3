"""RAGAS faithfulness / answer relevancy / context precision / context recall over the rows written by
`run_eval.py --with-tutor` (evaluation/results/last_ragas_rows.json).

IMPORTANT: the RAGAS API changes between versions. This script targets the classic `ragas.evaluate(Dataset, metrics=[...])`
interface; check the docs for your installed version (pip show ragas) and adapt imports/metric names if needed.
RAGAS needs an LLM + embeddings; configure them per its docs (e.g. a Gemini wrapper). Nothing here is pre-filled."""
import json
import sys

from _common import RESULTS, save_run


def main():
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError as e:
        raise SystemExit(f"Install ragas + datasets first ({e}). See the RAGAS docs for the current API.")
    rows = json.loads((RESULTS / "last_ragas_rows.json").read_text())
    rows = [r for r in rows if r["contexts"]]  # RAGAS cannot score answers that retrieved nothing
    ds = Dataset.from_list([{"question": r["question"], "answer": r["answer"], "contexts": r["contexts"],
                             "ground_truth": r["ground_truth"]} for r in rows])
    res = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
    metrics = {k: float(v) for k, v in res._repr_dict.items()} if hasattr(res, "_repr_dict") else dict(res)
    print(json.dumps(metrics, indent=2)); print("saved", save_run("ragas", {"n_rows": len(rows)}, metrics))


if __name__ == "__main__":
    sys.exit(main())
