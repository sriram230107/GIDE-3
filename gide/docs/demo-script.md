# Demo script (3–10 min video)

Total ~7 min. Prereqs: Postgres up, Redis up (`docker start gide-redis`), API :8000, worker, web :3000, course built.

1. **Upload (0:00–1:00)** — Sources page: upload attention.pdf. Show job → completed. Note warnings if any.
2. **Build knowledge (1:00–2:00)** — Build knowledge base; show chunks tagged per page, no prerequisite cycles (map page).
3. **Grounded chat (2:00–4:00)** — Tutor: ask "What is scaled dot-product attention?" Show GROUNDED badge, click citation [1] → SourceViewer opens the exact page.
4. **Off-material refusal (4:00–5:00)** — Ask "Who won the 2024 election?" Show NOT_COVERED refusal with no citations.
5. **Quiz (5:00–6:00)** — Assessments: generate 6-question quiz; answer one; show feedback + mastery before → after.
6. **Report + architecture (6:00–7:00)** — Assessment report (weak concepts, misconceptions); dashboard mastery change + AI-providers card; close on architecture diagram (docs/architecture.md).
