# GIDE — Project Status

Honest record of what is done, partial, blocked, deferred, and provisional.
Nothing below is claimed as verified end to end unless a saved log proves it.

## Done and unit-tested

- **Baseline (T1):** venv (Python 3.12), 37 pytest passed, API + worker + frontend started (`evidence/step1/pytest.log`).
- **LLM layer (T2–T4):** dual-provider interface (Ollama/Gemini) with per-provider
  semaphore, retry with backoff + jitter, JSON repair; `embedding_model` stored on
  chunks/concepts/questions with "rebuild required" refusal on mismatch;
  `/health` + `/api/system/models` report per-capability provider/model/reachable/installed.
  Stub-HTTP tests pass. Live latencies measured and saved in `evidence/t4/live_calls.log`:
  text (ollama/qwen2.5:3b) 2.68 s, embed (ollama/nomic-embed-text, dim 768) 1.08 s,
  vision (gemini flash) 32.77 s. Recommendation: Ollama for build/tutor/quiz, Gemini for vision.
- **Retrieval eval (T9):** 11 candidate Q/A pairs from the attention paper
  (`evidence/step4/candidate_questions.json`, PROVISIONAL); lexical-only proxy hit@1 0.8182,
  hit@3 0.9091, hit@5 1.0, MRR 0.8864, seed 7.
- **Study scheduler (T10):** `exam_plan()` pure function reusing the study director,
  `GET /api/learner/{course_id}/exam-plan`, `/plan` page; tests pass; web build passes.
- **Flashcards (T11):** verified short-answer questions on weak concepts with citations,
  `GET /api/learner/{course_id}/flashcards`, `/flashcards` page; tests pass; web build passes.
- **Question audit (T12):** `audit_error_rate` (unclear marks excluded), mark endpoints,
  `/audit` page; tests pass; web build passes. No schema change (uses existing JSONB column).
- **Polish (T13):** loading/empty/error states on all pages, responsive layouts,
  startup logging, corrected README.
- **Docs (T14):** architecture, grounding, and learner-model docs match the code;
  evaluation report with real tables; demo script.

## Partial (code + unit tests done, live run missing)

- **Ingest + build (T5):** both staged PDFs parse and chunk DB-free
  (attention 551 units → 74 chunks; ML 306 units → 195 chunks; 100% page-tagged;
  cycle-guard spot-check passes). Live ingest + build-knowledge run is BLOCKED (see below).
- **Citations + tutor (T6):** provenance regression tests pass.
  Live 10-citation spot-check + 5 tutor questions (2 off-topic) not run — BLOCKED.
- **Assessments (T7):** live generate+verify per question type ran against one paper page
  with qwen2.5:3b: **mcq FAIL (solver disagrees), short FAIL (solver disagrees),
  numeric SKIP (nothing to compute — correct). Verification pass rate: 0/2 attempted**
  (negative result; prompts were not tuned to look good). Full diagnostic/quiz service
  path + stats endpoint not run — BLOCKED.
- **Frontend (T8):** `npm run build` passes (all routes compile); every client API call
  maps to a server route (27 paths). Live curl of page routes — BLOCKED. Visual
  click-through: Untested.

## BLOCKED

- **Live knowledge build:** Postgres was unavailable for most of the project
  (5432 REFUSED); a local instance was eventually started and the API + worker came up,
  but the build log (`evidence/live/build.log`) still shows `ready: False` with
  0 chunks after ~15 minutes (slow CPU embedding phase). Everything downstream —
  live citation/tutor checks, full assessment service path, real `run_eval.py` hit@k,
  live exam-plan/flashcards/audit flows — waits on a finished build.
- **PPTX ingestion:** `samples.office.com` DNS unresolvable; no openly licensed PPTX staged.
- **Video ingestion:** only reachable sample was 96 MB, too large for a CPU-only session;
  no 2–3 min openly licensed video staged.
- DB-gated pytest files (`test_db_check_constraint`, `test_e2e_pdf_ingestion`) never ran green.

## DEFERRED (see `docs/FUTURE.md` — never started)

RAGAS evaluation and the custom Ollama judge wrapper; `calibrate.py` / `simulate.py`
end-to-end runs; `--no-lexical` ablation; Learning Replay chart; 3D Explore;
Hindi/mixed-language support; any new provider, model, runtime component, or refactor.

## PROVISIONAL (auto-generated, unreviewed — not verified results)

- `evidence/step4/candidate_questions.json` (11 Q/A pairs derived from parsed chunks).
- T9 hit@k figures (lexical-only proxy of `run_eval.py`, seed 7 — no DB, no embeddings).
