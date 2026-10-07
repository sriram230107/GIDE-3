"""Simulated-student evaluation (Req 5c). Pure Python, no DB or LLM:

  python evaluation/simulate.py [--seeds 40]

Runs 4 hidden-truth student profiles x 4 policies (same students for every policy) and writes JSON + a markdown table
to evaluation/results/. The estimator is the production learner model (app.learner.model). Read the limits in
app/learner/simulator.py before quoting any number."""
import argparse
import json

from _common import RESULTS, save_run


def main(seeds: int):
    from app.learner.simulator import PROFILES, paired_difference, run_experiment
    r = run_experiment(seeds=seeds)
    comparisons = [paired_difference(a, b, "gain", seeds=seeds) for a, b in
                   [("adaptive", "random"), ("adaptive", "random_norepeat"), ("adaptive", "adaptive_noforget"),
                    ("adaptive_noforget", "random_norepeat")]]
    comparisons.append(paired_difference("adaptive", "random_norepeat", "mae", seeds=seeds))
    lines = ["| policy | knowledge gain | final known | estimation MAE | repetition rate |", "|---|---|---|---|---|"]
    for pol, d in r["_overall"].items():
        lines.append(f"| {pol} | {d['gain'][0]:.3f} +/- {d['gain'][1]:.3f} | {d['end_known'][0]:.3f} | {d['mae'][0]:.3f} | {d['repetition_rate'][0]:.3f} |")
    md = "\n".join(lines)
    p = save_run("simulation", r["_config"], {"results": r, "paired": comparisons})
    (RESULTS / (p.stem + ".md")).write_text(md + "\n\nPaired differences (A-B, 95% CI):\n" + "\n".join(map(str, comparisons)))
    print(md); print(*comparisons, sep="\n"); print("saved", p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, default=100)
    main(ap.parse_args().seeds)
