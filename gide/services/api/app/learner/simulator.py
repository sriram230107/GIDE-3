"""Simulated students for evaluating personalization (Req 5c).

A hidden ground-truth knowledge state per concept evolves with learning and forgetting. Four policies
answer the same questions against the SAME hidden students (same seeds):
  random            random concept, random item WITH replacement (naive non-adaptive baseline)
  random_norepeat   random concept, random unseen item
  adaptive_noforget the real learner model + director priority, forgetting ignored
  adaptive          the real learner model + director priority incl. forgetting risk
All arms update the same BKT estimator from their own answers, so estimation error is comparable.

LIMITS (state these in any report): simulated students validate the mechanics only. Results depend on the
assumed learning/forgetting/guess/slip parameters and say nothing about real learning gains.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from app.learner import model as lm
from app.learner.director import concept_priority, target_difficulty


@dataclass
class Profile:
    name: str
    learn_rate: float      # P(learn an unknown concept after practising it with feedback, prereqs known)
    forget_days: float     # true mean retention time (days) of a known concept
    init_known: float      # fraction of concepts known at the start
    guess_mult: float = 1.0
    slip_add: float = 0.0


PROFILES = [
    Profile("novice", learn_rate=0.25, forget_days=10, init_known=0.05),
    Profile("average", learn_rate=0.35, forget_days=20, init_known=0.25),
    Profile("fast-forgetful", learn_rate=0.50, forget_days=5, init_known=0.15),
    Profile("strong-careless", learn_rate=0.40, forget_days=30, init_known=0.55, slip_add=0.08),
]


@dataclass
class World:
    n_concepts: int
    prereqs: dict[int, list[int]]
    bank: dict[int, list[float]]  # concept -> difficulties of its items (item index = position)


def make_world(rng: random.Random, n_concepts: int = 12, items_per_concept: int = 12) -> World:
    prereqs: dict[int, list[int]] = {}
    for c in range(n_concepts):
        cands = list(range(c))
        k = 0 if c == 0 else rng.choice([0, 1, 1, 2])
        prereqs[c] = rng.sample(cands, min(k, len(cands)))
    bank = {c: [float(rng.randint(1, 5)) for _ in range(items_per_concept)] for c in range(n_concepts)}
    return World(n_concepts, prereqs, bank)


@dataclass
class Student:
    profile: Profile
    known: list[bool]
    rng: random.Random

    def answer(self, concept: int, difficulty: float) -> bool:
        guess, slip = lm.item_params("mcq", difficulty)
        guess = min(0.6, guess * self.profile.guess_mult)
        slip = min(0.6, slip + self.profile.slip_add)
        p = (1 - slip) if self.known[concept] else guess
        return self.rng.random() < p

    def practise(self, world: World, concept: int) -> None:
        if self.known[concept]:
            return
        ready = all(self.known[p] for p in world.prereqs[concept])
        p = self.profile.learn_rate * (1.0 if ready else 0.4)
        if self.rng.random() < p:
            self.known[concept] = True

    def pass_days(self, days: float) -> None:
        p_forget = 1 - math.exp(-days / self.profile.forget_days)
        for c, k in enumerate(self.known):
            if k and self.rng.random() < p_forget:
                self.known[c] = False


class Tracker:
    """The estimator under test: per-concept BKT + stability, as in the production learner service."""

    def __init__(self, n: int, use_forgetting: bool):
        self.p = [lm.P_INIT] * n
        self.stab = [lm.STABILITY_INIT] * n
        self.last_day: list[Optional[float]] = [None] * n
        self.last_wrong_day: list[Optional[float]] = [None] * n
        self.attempts = [0] * n
        self.use_forgetting = use_forgetting

    def eff(self, c: int, day: float) -> float:
        if not self.use_forgetting or self.last_day[c] is None:
            return self.p[c]
        return lm.effective_mastery(self.p[c], day - self.last_day[c], self.stab[c])

    def risk(self, c: int, day: float) -> float:
        if not self.use_forgetting or self.last_day[c] is None:
            return 0.0
        return lm.forgetting_risk(day - self.last_day[c], self.stab[c])

    def observe(self, c: int, correct: bool, difficulty: float, day: float) -> None:
        self.p[c] = lm.update_mastery(self.p[c], correct, "quiz", "mcq", difficulty)
        self.stab[c] = lm.update_stability(self.stab[c], correct, "quiz")
        self.last_day[c] = day
        self.attempts[c] += 1
        if not correct:
            self.last_wrong_day[c] = day


def _pick_adaptive(world: World, tr: Tracker, day: float, used: dict[int, set[int]]) -> Optional[tuple[int, int]]:
    n = world.n_concepts
    eff = [tr.eff(c, day) for c in range(n)]
    dependents: dict[int, list[int]] = {c: [] for c in range(n)}
    for c, ps in world.prereqs.items():
        for p in ps:
            dependents[p].append(c)
    best, best_s = None, -1.0
    for c in range(n):
        if len(used[c]) >= len(world.bank[c]):
            continue
        lw = tr.last_wrong_day[c]
        info = {"eff": eff[c], "risk": tr.risk(c, day),
                "unlocks": sum(1 for d in dependents[c] if eff[d] < 0.6),
                "recent_wrong": 1.0 if (lw is not None and day - lw <= 3) else 0.0,
                "prereq_weak": any(eff[p] < 0.5 for p in world.prereqs[c])}
        s = concept_priority(info)
        if tr.attempts[c] == 0:
            s += 0.05  # mild exploration bonus for never-seen concepts
        if s > best_s:
            best, best_s = c, s
    if best is None:
        return None
    tgt = target_difficulty(eff[best], "adaptive")
    unseen = [i for i in range(len(world.bank[best])) if i not in used[best]]
    item = min(unseen, key=lambda i: abs(world.bank[best][i] - tgt))
    return best, item


def run_one(policy: str, profile: Profile, seed: int, sessions: int = 6, per_session: int = 10,
            gap_days: float = 2.0) -> dict:
    world_rng = random.Random(seed)
    world = make_world(world_rng)
    s_rng = random.Random(seed * 7919 + 1)
    known0 = [s_rng.random() < profile.init_known for _ in range(world.n_concepts)]
    st = Student(profile, known0[:], random.Random(seed * 104729 + 3))
    pick_rng = random.Random(seed * 31 + 5)
    tr = Tracker(world.n_concepts, use_forgetting=(policy == "adaptive"))
    used: dict[int, set[int]] = {c: set() for c in range(world.n_concepts)}
    asked = repeats = 0
    day = 0.0
    for _ in range(sessions):
        for _q in range(per_session):
            if policy == "random":
                c = pick_rng.randrange(world.n_concepts)
                i = pick_rng.randrange(len(world.bank[c]))
            elif policy == "random_norepeat":
                opts = [c for c in range(world.n_concepts) if len(used[c]) < len(world.bank[c])]
                if not opts:
                    break
                c = pick_rng.choice(opts)
                i = pick_rng.choice([x for x in range(len(world.bank[c])) if x not in used[c]])
            else:
                pk = _pick_adaptive(world, tr, day, used)
                if pk is None:
                    break
                c, i = pk
            asked += 1
            if i in used[c]:
                repeats += 1
            used[c].add(i)
            d = world.bank[c][i]
            correct = st.answer(c, d)
            tr.observe(c, correct, d, day)
            st.practise(world, c)  # feedback shown after every answer
        day += gap_days
        st.pass_days(gap_days)
    n = world.n_concepts
    end_known = sum(st.known) / n
    start_known = sum(known0) / n
    mae = sum(abs(tr.eff(c, day) - (1.0 if st.known[c] else 0.0)) for c in range(n)) / n
    return {"start_known": start_known, "end_known": end_known, "gain": end_known - start_known,
            "mae": mae, "repetition_rate": (repeats / asked) if asked else 0.0, "asked": asked}


POLICIES = ["random", "random_norepeat", "adaptive_noforget", "adaptive"]


def _policy_impl(name: str) -> str:
    return "adaptive_noforget" if name == "adaptive_noforget" else name


def run_experiment(seeds: int = 40, sessions: int = 6, per_session: int = 10, gap_days: float = 2.0) -> dict:
    """Returns {profile: {policy: {metric: (mean, sd)}}, '_overall': ...}. Same seeds for every policy."""
    def agg(vals):
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
        return round(m, 4), round(sd, 4)

    out: dict = {}
    overall: dict[str, dict[str, list[float]]] = {p: {} for p in POLICIES}
    for prof in PROFILES:
        out[prof.name] = {}
        for pol in POLICIES:
            runs = [run_one(_policy_impl(pol), prof, seed, sessions, per_session, gap_days) for seed in range(seeds)]
            out[prof.name][pol] = {k: agg([r[k] for r in runs]) for k in ("gain", "end_known", "mae", "repetition_rate")}
            for k in ("gain", "end_known", "mae", "repetition_rate"):
                overall[pol].setdefault(k, []).extend(r[k] for r in runs)
    out["_overall"] = {pol: {k: agg(v) for k, v in d.items()} for pol, d in overall.items()}
    out["_config"] = {"seeds": seeds, "sessions": sessions, "questions_per_session": per_session,
                      "gap_days": gap_days, "n_concepts": 12, "items_per_concept": 12}
    return out


def paired_difference(pol_a: str, pol_b: str, metric: str = "gain", seeds: int = 100,
                      sessions: int = 6, per_session: int = 10, gap_days: float = 2.0) -> dict:
    """Mean of (A - B) over identical (profile, seed) students with a normal-approx 95% CI."""
    diffs = []
    for prof in PROFILES:
        for seed in range(seeds):
            a = run_one(_policy_impl(pol_a), prof, seed, sessions, per_session, gap_days)[metric]
            b = run_one(_policy_impl(pol_b), prof, seed, sessions, per_session, gap_days)[metric]
            diffs.append(a - b)
    n = len(diffs)
    m = sum(diffs) / n
    sd = math.sqrt(sum((d - m) ** 2 for d in diffs) / (n - 1))
    se = sd / math.sqrt(n)
    return {"a": pol_a, "b": pol_b, "metric": metric, "n_students": n, "mean_diff": round(m, 4),
            "ci95": (round(m - 1.96 * se, 4), round(m + 1.96 * se, 4))}
