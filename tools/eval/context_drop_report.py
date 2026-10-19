#!/usr/bin/env python3
"""
Summarise context_drop_eval.py results: python3 tools/eval/context_drop_report.py <jsonl> [<jsonl> ...] > report.md

kept = (nll_none - nll) / (nll_none - nll_full): the share of what the context is worth (in log-likelihood of the
real bars) that a policy keeps at a budget. 1 = as good as all context, 0 = as bad as none. dnll = (nll - nll_full)
per target token. Cases where the context is worth less than 2 nats are left out of `kept` (too noisy).
"""
import collections, json, sys

import numpy as np

MIN_SPAN = 2.0


def boot(xs, n=1000, seed=0):
    xs = np.asarray(xs)
    rng = np.random.default_rng(seed)
    m = xs[rng.integers(0, len(xs), (n, len(xs)))].mean(1)
    return xs.mean(), np.percentile(m, 2.5), np.percentile(m, 97.5)


def main():
    rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
    errors = [r for r in rows if r.get("policy") == "_error"]
    rows = [r for r in rows if not r.get("policy", "_").startswith("_") and r.get("nll") is not None]
    for r in rows:
        span = r["nll_none"] - r["nll_full"]
        r["kept"] = (r["nll_none"] - r["nll"]) / span if span >= MIN_SPAN else None
        r["dnll"] = (r["nll"] - r["nll_full"]) / r["cont"]
        r["kind"] = ("cont" if r["ar"] else "fill") + ("_drum" if r["drums"] else "_mel")
    print("# Context-drop policies\n")
    print(f"{len({(r['piece'], r['task'], r['model'], r['dim']) for r in rows})} cases, {len(errors)} errors.\n")
    by_md = collections.defaultdict(list)
    for r in rows:
        by_md[(r["model"], r["dim"])].append(r)
    for (model, dim), grp in sorted(by_md.items()):
        print(f"## {model}, {dim}-bar window\n")
        for budget in ("f0.25", "f0.5", "f0.75", "fit"):
            g = [r for r in grp if r["budget"] == budget]
            if not g:
                continue
            pol = collections.defaultdict(list)
            for r in g:
                pol[r["policy"]].append(r)
            # paired win rate against B on the same case
            ref = {(r["piece"], r["task"]): r["nll"] for r in pol.get("B", [])}
            lines = []
            for p, rs in pol.items():
                kept = [r["kept"] for r in rs if r["kept"] is not None]
                k = boot(kept) if kept else (float("nan"),) * 3
                d = np.mean([r["dnll"] for r in rs])
                pairs = [(r["nll"], ref[(r["piece"], r["task"])]) for r in rs if (r["piece"], r["task"]) in ref]
                win = np.mean([a < b - 1e-6 for a, b in pairs]) if pairs else float("nan")
                lose = np.mean([a > b + 1e-6 for a, b in pairs]) if pairs else float("nan")
                by_kind = {kd: np.mean([r["kept"] for r in rs if r["kind"] == kd and r["kept"] is not None] or [np.nan])
                           for kd in ("fill_mel", "fill_drum", "cont_mel", "cont_drum")}
                lines.append((k[0], p, k, d, win, lose, len(rs), by_kind,
                              np.mean([r["prompt"] / r["budget_tokens"] for r in rs])))
            lines.sort(key=lambda x: -np.nan_to_num(x[0], nan=-9))
            label = {"fit": "real budget (the full step overflows)"}.get(budget, f"drop at least {budget[1:]} of the context tokens")
            print(f"### {label}\n")
            print("| policy | kept | 95% CI | ΔNLL/token | beats B | loses to B | fill mel | fill drum | cont mel | cont drum | prompt/budget | n |")
            print("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for m, p, k, d, win, lose, n, bk, fillr in lines:
                print(f"| {p} | {k[0]:.3f} | {k[1]:.3f}–{k[2]:.3f} | {d:.3f} | {win:.0%} | {lose:.0%} | "
                      + " | ".join(f"{bk[x]:.2f}" for x in ("fill_mel", "fill_drum", "cont_mel", "cont_drum"))
                      + f" | {fillr:.2f} | {n} |")
            print()
        half = [r for r in grp if r["policy"] == "dim_half"]
        if half:
            kept = [r["kept"] for r in half if r["kept"] is not None]
            print(f"Half window, no drops (today's step-down), infill only: kept {np.mean(kept):.3f}, prompt "
                  f"{np.mean([r['prompt'] / r['full_prompt'] for r in half]):.0%} of the full one, n {len(half)}.\n")


if __name__ == "__main__":
    main()
