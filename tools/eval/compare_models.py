#!/usr/bin/env python3
"""
Summarise tools/eval/model_eval.py results: per model and task, the mean of each metric with a 95% bootstrap
interval, and a paired comparison with a reference model on the prompts both completed.

  python3 tools/eval/compare_models.py dist/eval/out [--ref yellow_medium]
"""
import argparse, glob, json, os
from collections import defaultdict

import numpy as np

METRICS = [  # name, how to read it, higher is better?
    ("f1", "notes matching the original (pitch+onset)", True),
    ("onset_sim", "rhythm profile vs original", True),
    ("pc_sim", "pitch-class profile vs original", True),
    ("key_fit_gen", "notes in the context's key", True),
    ("abs_density", "|log density ratio| vs original", False),
    ("pitch_mean_err", "mean pitch error (semitones)", False),
    ("kit_sim", "drum kit pieces vs original", True),
    ("s", "seconds per task", False),
]


def load(d):
    rows = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        for r in map(json.loads, open(f)):
            if r.get("ok") and "density_logratio" in r:
                r["abs_density"] = abs(r["density_logratio"])
            rows[r["model"]].append(r)
    return rows


def boot(x, n=2000, seed=0):
    x = np.asarray([v for v in x if v is not None and not np.isnan(v)], float)
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(seed)
    m = rng.choice(x, (n, len(x))).mean(1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), len(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--ref", default="yellow_medium")
    a = ap.parse_args()
    rows = load(a.dir)
    models = sorted(rows, key=lambda m: (not m.startswith("yellow"), m))
    tasks = sorted({r["task"] for m in rows for r in rows[m]})
    out = {"models": models, "tasks": tasks, "summary": {}, "paired": {}, "robust": {}}

    print("== robustness (all tasks)")
    for m in models:
        rs = rows[m]
        ok = [r for r in rs if r.get("ok")]
        tr = [r for r in ok if r.get("truncated")]
        errs = defaultdict(int)
        for r in rs:
            if not r.get("ok"):
                errs[r.get("error", "")[:60]] += 1
        out["robust"][m] = {"n": len(rs), "ok": len(ok), "truncated": len(tr), "errors": dict(errs),
                            "tok_s": float(np.mean([r["tokens"] / r["s"] for r in ok if r["s"] > 0])) if ok else None}
        print("%-24s %3d/%3d ok, %2d truncated, %.0f tok/s  %s" % (m, len(ok), len(rs), len(tr), out["robust"][m]["tok_s"] or 0, dict(errs) or ""))

    for task in tasks:
        print("\n== %s" % task)
        print("%-24s " % "model" + " ".join("%17s" % k for k, _, _ in METRICS))
        for m in models:
            rs = [r for r in rows[m] if r["task"] == task and r.get("ok")]
            if not rs:
                continue
            cells, summ = [], {}
            for k, _, _ in METRICS:
                mu, lo, hi, n = boot([r.get(k) for r in rs])
                summ[k] = [mu, lo, hi, n]
                cells.append("%6.3f [%4.2f,%4.2f]" % (mu, lo, hi) if n else "%17s" % "-")
            out["summary"]["%s|%s" % (m, task)] = summ
            print("%-24s " % m + " ".join("%17s" % c for c in cells))

    # paired: same piece + task, model minus reference
    print("\n== paired vs %s (mean difference [95%%], wins/losses on that metric)" % a.ref)
    ref = {(r["piece"], r["task"]): r for r in rows.get(a.ref, []) if r.get("ok")}
    for m in models:
        if m == a.ref:
            continue
        for task in tasks:
            pairs = [(r, ref[(r["piece"], r["task"])]) for r in rows[m] if r.get("ok") and r["task"] == task and (r["piece"], r["task"]) in ref]
            if not pairs:
                continue
            line = []
            for k, _, better_high in METRICS:
                d = [x.get(k) - y.get(k) for x, y in pairs if x.get(k) is not None and y.get(k) is not None]
                if not d:
                    continue
                mu, lo, hi, n = boot(d)
                win = sum(1 for v in d if (v > 0) == better_high and v != 0); loss = sum(1 for v in d if (v < 0) == better_high and v != 0)
                sig = "+" if (lo > 0) == better_high and (lo > 0 or hi < 0) else ("-" if (lo > 0 or hi < 0) else " ")
                out["paired"]["%s|%s|%s" % (m, task, k)] = [mu, lo, hi, n, win, loss]
                line.append("%s %+.3f%s" % (k, mu, sig))
            print("%-24s %-12s n=%-3d %s" % (m, task, len(pairs), "  ".join(line)))
    json.dump(out, open(os.path.join(a.dir, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
