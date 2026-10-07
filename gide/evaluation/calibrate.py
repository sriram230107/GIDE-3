"""Calibrate the grounding gate on the test set and write evaluation/calibration.json (read by the tutor).

  python evaluation/calibrate.py --course-id <uuid> --testset evaluation/testset.json

dense_min  : max-F1 separation of answerable vs off-material top-chunk cosine.
dense_high : smallest threshold at which >=90% of retrieved-as-confident items are answerable
             (answerable vs off-material+ambiguous); falls back to dense_min + 0.08 and says so.
Calibrate on one split and evaluate on another (or report the overlap honestly)."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from _common import ROOT, load_testset, save_run
from metrics import best_threshold


async def main(a):
    from app.core.database import AsyncSessionLocal
    from app.retrieval.search import hybrid_search
    items = load_testset(a.testset)
    tops = {}
    async with AsyncSessionLocal() as s:
        for it in items:
            hits = await hybrid_search(s, UUID(a.course_id), it["question"], k=5)
            tops[it["id"]] = max((h.dense for h in hits), default=0.0)
    pos = [tops[i["id"]] for i in items if i["bucket"] == "answerable"]
    neg = [tops[i["id"]] for i in items if i["bucket"] == "off_material"]
    mid = [tops[i["id"]] for i in items if i["bucket"] == "ambiguous"]
    lo = best_threshold(pos, neg)
    if not lo:
        raise SystemExit("need both answerable and off_material items")
    hi_info, note = None, ""
    for t in sorted(set(pos + neg + mid)):
        if t < lo["threshold"]:
            continue
        tp = sum(1 for x in pos if x >= t); fp = sum(1 for x in neg + mid if x >= t)
        if tp and tp / (tp + fp) >= 0.90:
            hi_info = t; break
    if hi_info is None:
        hi_info, note = lo["threshold"] + 0.08, "fallback: no threshold reached 90% precision for GROUNDED"
    out = {"dense_min": round(lo["threshold"], 4), "dense_high": round(hi_info, 4), "note": note,
           "calibrated_on": {"date": datetime.now(timezone.utc).isoformat(), "n_answerable": len(pos), "n_off": len(neg),
                             "n_ambiguous": len(mid), "f1_at_dense_min": lo["f1"]}}
    (ROOT / "evaluation" / "calibration.json").write_text(json.dumps(out, indent=2))
    save_run("calibration", {"testset": a.testset}, out)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--course-id", required=True); ap.add_argument("--testset", default="evaluation/testset.json")
    asyncio.run(main(ap.parse_args()))
