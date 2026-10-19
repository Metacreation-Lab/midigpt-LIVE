#!/usr/bin/env python3
"""
Vary strategies on held-out GigaMIDI pieces: the same 8 bars (0-7 of a 16-bar segment) of one track re-generated
with each strategy, scored against the original. Pieces and tracks come from model_eval.py.

  python3 tools/eval/vary_eval.py --model yellow_medium --data <test parquet dir> --out <dir> --shard 0 --shards 4

Strategies (passes run one after another on the updated score):
  A  all 8 bars at once                          (1 pass, bars_per_step 8)
  B  bar by bar, left to right                   (1 pass, bars_per_step 1: untouched targets show their old notes)
  C  bar by bar, random order                    (as B, shuffle)
  D  two bars at a time                          (1 pass, bars_per_step 2)
  E  3 random groups                             (3 passes, each group at once, the others as context)
  F  even bars, then odd bars                    (2 passes)
  G  bar by bar, untouched targets hidden        (8 passes: bar k, with bars k+1.. masked; earlier ones are new)
  H  3 random groups at temperature 1.2          (as E)
"""
import argparse, json, os, random, time, traceback
from collections import Counter

import numpy as np

import model_eval as M
from midigpt.inference.config import GenerationRequest, InferenceConfig, TrackPrompt
from midigpt.inference.engine import InferenceEngine

TARGET = list(range(8))      # one 8-bar window: the current planner splits bars 4-11 at its grid line (bar 8)


def strategies(seed):
    rng = random.Random(seed)
    perm = TARGET[:]; rng.shuffle(perm)
    thirds = [sorted(perm[i::3]) for i in range(3)]
    one = lambda bps, shuffle=False: [dict(bars=TARGET, bps=bps, shuffle=shuffle)]
    return {
        "A_all_at_once": one(8), "B_bar_by_bar": one(1), "C_bar_random": one(1, True), "D_two_bars": one(2),
        "E_groups3": [dict(bars=g, bps=8) for g in thirds],
        "F_even_odd": [dict(bars=TARGET[0::2], bps=8), dict(bars=TARGET[1::2], bps=8)],
        "G_bar_hidden": [dict(bars=[b], bps=1, mask=[c for c in TARGET if c > b]) for b in TARGET],
        "H_groups3_hot": [dict(bars=g, bps=8, temperature=1.2) for g in thirds],
    }


def request(score, t, p, seed):
    return GenerationRequest(
        tracks=[TrackPrompt(id=i, bars=list(p["bars"]) if i == t else [], mask_bars=list(p.get("mask", [])) if i == t else [])
                for i in range(len(score.tracks))],
        config=InferenceConfig(model_dim=8, bars_per_step=p["bps"], tracks_per_step=1, shuffle=p.get("shuffle", False),
                               temperature=p.get("temperature", 1.0), seed=seed, max_attempts=3,
                               novelty_check=False, silence_check=True, mask_mode="attention"),
    )


def bars_of(score, t, res):
    g = max(1, res // 12)
    k = res / score.resolution
    return [[(n.pitch, round(n.onset_ticks * k / g)) for n in score.tracks[t].bars[b].notes] for b in TARGET]


def jacc(a, b):
    A, B = Counter(a), Counter(b)
    u = sum((A | B).values())
    return 1.0 if u == 0 else sum((A & B).values()) / u


def metrics(orig, gen, t, drum):
    o, r = bars_of(orig, t, orig.resolution), bars_of(gen, t, orig.resolution)
    flat = lambda bs: [(i, p, on) for i, bar in enumerate(bs) for p, on in bar]
    ssm = lambda bs: np.array([[jacc(a, b) for b in bs] for a in bs])
    iu = np.triu_indices(len(TARGET), 1)
    x, y = ssm(o)[iu], ssm(r)[iu]
    struct = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else None
    no, nr = sum(map(len, o)), sum(map(len, r))
    m = {"copied": float(np.mean([Counter(a) == Counter(b) for a, b in zip(o, r)])),
         "change": 1 - jacc(flat(o), flat(r)),
         "density_logratio": float(np.log((nr + 1) / (no + 1))),
         "structure": struct,
         "seams_gen": float(np.mean([jacc(r[i], r[i + 1]) for i in range(len(r) - 1)])),
         "seams_orig": float(np.mean([jacc(o[i], o[i + 1]) for i in range(len(o) - 1)])),
         "empty_bars": int(sum(1 for a, b in zip(o, r) if a and not b))}
    gen_r = gen.resample(orig.resolution) if gen.resolution != orig.resolution else gen
    tm = M.score_task(orig, gen_r, t, TARGET, drum)
    m.update({k: tm[k] for k in ("onset_sim", "pc_sim", "key_fit_gen", "key_fit_gt", "kit_sim") if k in tm})
    m["flat"] = flat(r)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yellow_medium")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pieces", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    eng = InferenceEngine.from_pretrained(a.model)
    pieces = M.load_pieces(a.data, a.pieces)
    path = os.path.join(a.out, "vary_%s_%d.jsonl" % (a.model, a.shard))
    done = {(r["piece"], r["role"], r["strategy"], r["seed"]) for r in map(json.loads, open(path))} if os.path.exists(path) else set()
    t0 = time.time()
    with open(path, "a") as out:
        for pi, p in enumerate(pieces):
            if pi % a.shards != a.shard:
                continue
            s = p["score"]
            roles = [("melodic", M.busiest(s, False, bars=TARGET)), ("accomp", M.busiest(s, False, 1, bars=TARGET)),
                     ("drums", M.busiest(s, True, bars=TARGET))]
            for role, t in roles:
                if t is None:
                    continue
                for sd in range(a.seeds):
                    seed = 100 * pi + sd
                    for name, passes in strategies(seed).items():
                        if (p["id"], role, name, sd) in done:
                            continue
                        rec = {"model": a.model, "piece": p["id"], "role": role, "strategy": name, "seed": sd,
                               "instrument": s.tracks[t].instrument}
                        t1 = time.time(); score = s; tokens = 0
                        try:
                            for k, ps in enumerate(passes):
                                sess = eng.session(score, request(score, t, ps, seed * 10 + k))
                                score = sess.run(); tokens += sess.gen_count
                            rec.update(ok=True, s=time.time() - t1, tokens=tokens, **metrics(s, score, t, role == "drums"))
                        except Exception as e:
                            rec.update(ok=False, s=time.time() - t1, error=str(e)[:300]); traceback.print_exc()
                        out.write(json.dumps(rec) + "\n"); out.flush()
            print("piece %d/%d %.0fs" % (pi + 1, len(pieces), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
