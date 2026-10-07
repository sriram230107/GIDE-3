# Grounding method

1. Hybrid retrieval: query embedding cosine over the course's chunk matrix + Postgres full-text (OR query), fused with reciprocal rank fusion.
2. Gate: if the best chunk's cosine < `dense_min` the tutor refuses (no LLM call). Thresholds come from `evaluation/calibration.json`
   written by `evaluation/calibrate.py`; until that exists the API reports `gate.calibrated = false` and the UI shows "gate UNCALIBRATED".
3. The model sees only numbered excerpts, must cite `[n]`, and self-reports coverage full / partial / none.
4. Citations are validated in code: markers pointing at non-existent excerpts are removed; an answer with zero valid citations is never GROUNDED.
5. Label = GROUNDED / PARTIAL / NOT_COVERED (`ai/tutor.py::decide_label`, unit-tested). No percentages are shown.
6. A citation is built from the chunk's primary ContentUnit, so it opens that unit's exact page, slide render or video timestamp.
7. General-knowledge answers are only produced when the student asks for them, and are labelled OUTSIDE_COURSE with no citations.

Known weaknesses: LLM coverage self-report can be wrong; chunk-level (not sentence-level) provenance; scanned/figure text depends on Gemini vision quality.
