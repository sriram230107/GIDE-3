# Learner model (as implemented in `services/api/app/learner/`)

**Mastery** per concept = BKT-style posterior (`model.py`). Parameters: P(init)=0.20, P(transit)=0.15, guess by question type
(MCQ 0.25, short 0.08, numeric 0.05) scaled down and slip scaled up with item difficulty (1-5).

**Evidence weights** (rule 4): verified quiz answer = 1.0, tutor check-for-understanding = 0.5, "student asked a question" = logged
but weight 0 in mastery until the simulator/real data validates a non-zero value. Response time is logged, never used.
Every event is stored in `evidence_events` (before/after, weight, metadata), so any mastery number is auditable.

**Forgetting** (heuristic, not fitted): stability S (days) grows x1.8 after a correct quiz answer (x1.4 for checks) and shrinks x0.6
after an error; retrievability R = exp(-days/S); effective mastery = p * (0.5 + 0.5 R); forgetting risk = 1 - R.

**Cold start**: self-rated intake per topic sets priors (new 0.10 / some 0.35 / comfortable 0.60, source recorded as `intake`),
and the diagnostic quiz samples up to 2 concepts per topic with balanced focus.

**Item difficulty**: LLM guess is a prior; blended with the observed error rate (shrinkage k=4) after attempts.

**Study director** (`director.py`): priority = 0.45(1-mastery) + 0.20 risk + 0.20 unlocks + 0.15 recent-wrong, x0.6 if a prerequisite is
weak. Each recommendation lists the numbers that produced it.

Not validated on real students. The simulator (`evaluation/simulate.py`) checks mechanics only.
