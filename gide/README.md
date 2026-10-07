# Gide: source-grounded adaptive tutor (Track D)

Next.js + FastAPI + PostgreSQL + Redis (Arq worker) + Gemini. No microservices.

## Run (Windows or Linux)
Prereqs: Python 3.11+, Node 20+, PostgreSQL (database `gide`), Redis, **ffmpeg** on PATH, **LibreOffice** (for PPTX slide images), Ollama (with qwen2.5:3b, llama3.1:8b, nomic-embed-text, llama3.2-vision), a Gemini API key.
```bash
# 1. backend
cd services/api
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # set DB password, JWT_SECRET, GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000                # tables are created on startup
# 2. worker (second terminal, same venv)
python run_worker.py
# 3. frontend (third terminal)
cd apps/web && npm install && npm run dev                # http://localhost:3000
```
Check `GET http://localhost:8000/api/system/models` (after logging in) to view per-capability status (provider, model, reachable, installed), also shown on the dashboard and in `GET /health` (`llm_status`). You can configure `TEXT_PROVIDER`, `EMBED_PROVIDER`, and `VISION_PROVIDER` (each `ollama|gemini`) in `.env`.

Measured live latencies (evidence/t4/live_calls.log): text ollama/qwen2.5:3b 2.68s, embed ollama/nomic-embed-text 1.08s, vision gemini/gemini-3.8-flash 32.77s. Recommendation: build (embed) + tutor/quiz drafts on Ollama (fast, local); vision on Gemini (no local vision model installed); reserve llama3.1:8b for final live measurements only.

## Workflow
Register -> create course -> Sources: upload PDF/PPTX/video/images -> wait for `completed` (read warnings) -> **Build knowledge base**
-> Tutor / Assessments / Knowledge map / Dashboard.
Rebuilding the knowledge base resets learner mastery for that course.

## Tests
```bash
cd services/api && pytest          # DB tests need Postgres up; parser/pure tests need none
python ../../evaluation/test_metrics.py   # or: pytest tests/test_eval_metrics.py
```
## Evaluation (do this on YOUR course material)
1. `cp evaluation/testset.TEMPLATE.json evaluation/testset.json` and write 40-60 answerable, 10-15 ambiguous, 10-15 off-material items with true source locations.
2. `python evaluation/calibrate.py --course-id <uuid>` (writes the grounding thresholds)
3. `python evaluation/run_eval.py --course-id <uuid> --with-tutor` (hit@k, MRR, citation accuracy, refusal precision/recall)
4. `python evaluation/ragas_eval.py` (RAGAS; check the installed ragas API first)
5. `python evaluation/simulate.py` (simulated students; needs nothing running)
Ablations: `--no-lexical` gives dense-only. Every run is saved under `evaluation/results/`.
Calibrating and evaluating on the same items overstates performance: split your test set.

## Deliberate deviations from the plan
- Embeddings are stored as float arrays and compared with numpy (course-sized corpora) instead of the pgvector extension, so native Windows Postgres needs no extension. Swap to pgvector if the corpus grows large.
- `create_all` instead of Alembic migrations: after a model change, drop the dev database.
- ASR is faster-whisper only (no silent LLM fallback). Gemini is used for vision/OCR, tutoring, question generation.
- Not built (see docs/FUTURE.md): RAGAS judge, calibrate/simulate end-to-end runs, --no-lexical ablation table, Learning Replay chart, 3D Explore, Hindi/mixed-language. Flashcards, study scheduler (/plan), question audit (/audit) and the dashboard AI-provider card are built (T10–T12, T4).
