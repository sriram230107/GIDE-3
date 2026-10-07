# Evaluation report (all numbers from saved evidence files; see paths)

## Retrieval (T9, PROVISIONAL)
Lexical-only proxy of run_eval hit@k over 11 auto-derived questions from attention.pdf pages (seed 7;
repo `_or_query` + `metrics.retrieval_metrics`; no DB/embeddings). Source: evidence/t9/retrieval_eval.log.

| metric | value |
|---|---|
| n | 11 |
| hit@1 | 0.8182 |
| hit@3 | 0.9091 |
| hit@5 | 1.0000 |
| MRR | 0.8864 |

PROVISIONAL (auto-generated, unreviewed): questions derived from chunk keywords, expected locations = source pages.
`run_eval.py` itself is BLOCKED on Postgres (needs AsyncSessionLocal + hybrid_search + eval_runs table).

## Assessment generation + verification (T7)
Live generate→verify per qtype vs attention.pdf p.2, qwen2.5:3b. Source: evidence/t7/assess_live.json.

| qtype | generate | verify | outcome |
|---|---|---|---|
| mcq | 122.6 s | 61.5 s | FAIL (solver-disagrees) |
| short | 43.3 s | 58.2 s | FAIL (solver-disagrees) |
| numeric | 11.1 s | — | SKIP (nothing to compute; correct — no formula on p.2) |

Verification pass rate: 0/2 attempted. Cause (not prompt-tuned): 3b solver disagrees with 3b generator on
paraphrase-heavy stems — small-model self-verification noise, not a code bug (structure checks passed).
Full diagnostic/quiz path + GET stats/{course_id}: BLOCKED on Postgres.

## Negative results
- No live ingest→build→tutor→quiz run exists yet: every live path needs Postgres 5432, which refused all sessions.
- Gate calibration never ran (calibrate.py deferred; gate reports UNCALIBRATED).
- Self-verification with qwen2.5:3b rejects its own questions (above) — reserve llama3.1:8b for final measurements.

## BLOCKED / DEFERRED / PROVISIONAL / Untested
- BLOCKED: Postgres-backed runs (T5 live build, T6 spot-checks, T7 service path, run_eval); PPTX download (DNS); full video ingest (96 MB sample).
- DEFERRED: see docs/FUTURE.md (RAGAS + judge, calibrate/simulate e2e, --no-lexical ablation, Replay chart, 3D/Hindi, new providers).
- PROVISIONAL: evidence/step4/candidate_questions.json (auto-generated, unreviewed).
- Untested: visual click-through of all pages; live API curl (DB down); RAGAS; simulator output on real data.
