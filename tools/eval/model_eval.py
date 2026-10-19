#!/usr/bin/env python3
"""
Compare MIDI-GPT checkpoints on held-out GigaMIDI pieces: the same prompts, seeds and tasks for every model,
scored against the original bars.

  python3 tools/eval/model_eval.py --model prism_medium|<name>=<checkpoint.safetensors> --data <test parquet dir> --out <dir> [--pieces 64]

Writes <out>/<model>.jsonl (one line per task) and <out>/midi/<model>/<piece>_<task>.mid for listening.

Tasks, on a 16-bar segment of each piece:
  infill2      bars 6-7 of the busiest melodic track, model_dim 8, bars_per_step 2
  drums2       bars 6-7 of the busiest drum track
  track8       bars 4-11 of the second-busiest melodic track at once (an accompaniment part)
  cont8        bars 8-15 of the busiest melodic track, autoregressive after its bars 0-7 (bars_per_step 4)
  infill2_w16  infill2 with model_dim 16 (prism / expressive only: they have 12- and 16-bar windows)
"""
import argparse, glob, json, os, random, time, traceback
from collections import Counter

import numpy as np
import pyarrow.parquet as pq

from midigpt._types import Score
from midigpt.inference.config import GenerationRequest, InferenceConfig, TrackPrompt
from midigpt.inference.engine import InferenceEngine

SEG = 16


def load_pieces(data_dir, n, seed=0):
    """n test pieces with 3-12 tracks, >= 300 notes and 4/4 for SEG bars, picked the same way for every model."""
    rng = random.Random(seed)
    files = sorted(glob.glob(os.path.join(data_dir, "*.parquet")))
    rows = []
    for f in files:
        t = pq.read_table(f, columns=["md5", "num_tracks", "total_notes"]).to_pylist()
        rows += [(f, i, r) for i, r in enumerate(t) if 3 <= (r["num_tracks"] or 0) <= 12 and (r["total_notes"] or 0) >= 300]
    rng.shuffle(rows)
    out = []
    tables = {}
    for f, i, r in rows:
        if len(out) >= n:
            break
        if f not in tables:
            tables[f] = pq.read_table(f, columns=["music", "md5", "music_styles_curated"])
        rec = tables[f].slice(i, 1).to_pylist()[0]
        try:
            score = Score.from_bytes(rec["music"])
        except Exception:
            continue
        seg = segment(score)
        if seg is None:
            continue
        out.append({"id": rec["md5"][:10], "styles": rec["music_styles_curated"], "score": seg})
    return out


def segment(score):
    """SEG bars of 4/4 with at least 2 melodic tracks that play in them; starts at bar 8 when the piece is long enough."""
    nb = min(len(t.bars) for t in score.tracks) if score.tracks else 0
    for start in ([8, 0] if nb >= 8 + SEG else [0]):
        if nb < start + SEG:
            continue
        bars = range(start, start + SEG)
        if any((score.tracks[0].bars[b].ts_numerator, score.tracks[0].bars[b].ts_denominator) != (4, 4) for b in bars):
            continue
        s = Score(tracks=[], resolution=score.resolution, tempo=score.tempo)
        for t in score.tracks:
            tr = type(t)(bars=[t.bars[b] for b in bars], instrument=t.instrument, track_type=t.track_type)
            if sum(len(b.notes) for b in tr.bars) > 0:
                s.tracks.append(tr)
        mel = [t for t in s.tracks if t.track_type != "drum"]
        if len(mel) >= 2 and 3 <= len(s.tracks) <= 12:
            return s
    return None


def busiest(score, drum, k=0, bars=range(SEG)):
    ts = [(sum(len(t.bars[b].notes) for b in bars), i) for i, t in enumerate(score.tracks) if (t.track_type == "drum") == drum]
    ts.sort(reverse=True)
    return ts[k][1] if len(ts) > k and ts[k][0] > 0 else None


def tasks(score, families):
    m0, m1, d0 = busiest(score, False), busiest(score, False, 1), busiest(score, True)
    out = [("infill2", m0, [6, 7], False, 8, 2), ("track8", m1, list(range(4, 12)), False, 8, 8),
           ("cont8", m0, list(range(8, 16)), True, 8, 4)]
    if d0 is not None:
        out.insert(1, ("drums2", d0, [6, 7], False, 8, 2))
    if "16" in families:
        out.append(("infill2_w16", m0, [6, 7], False, 16, 2))
    return [t for t in out if t[1] is not None]


# ---------------------------------------------------------------- metrics

def notes(score, t, bars):
    return [(b, n) for b in bars for n in score.tracks[t].bars[b].notes]


def grid(score):
    return max(1, score.resolution // 12)


def pc_hist(ns):
    h = np.zeros(12)
    for _, n in ns:
        h[n.pitch % 12] += 1
    return h


def cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 and nb == 0:
        return 1.0
    return 0.0 if na == 0 or nb == 0 else float(a @ b / na / nb)


def onset_hist(ns, score):
    bar = score.resolution * 4
    h = np.zeros(48)
    for _, n in ns:
        h[int(n.onset_ticks % bar * 48 // bar)] += 1
    return h


def key_set(score, t, bars):
    """The 7 most used pitch classes of every melodic note except the target bars of the target track."""
    h = np.zeros(12)
    for i, tr in enumerate(score.tracks):
        if tr.track_type == "drum":
            continue
        for b in range(SEG):
            if i == t and b in bars:
                continue
            for n in tr.bars[b].notes:
                h[n.pitch % 12] += 1
    return set(np.argsort(-h)[:7])


def f1(gt, gen, g):
    A = Counter((b, n.pitch, round(n.onset_ticks / g)) for b, n in gt)
    B = Counter((b, n.pitch, round(n.onset_ticks / g)) for b, n in gen)
    tp = sum((A & B).values())
    p = tp / max(1, sum(B.values())); r = tp / max(1, sum(A.values()))
    return 0.0 if tp == 0 else 2 * p * r / (p + r)


def polyphony(ns, g):
    c = Counter((b, round(n.onset_ticks / g)) for b, n in ns)
    return float(np.mean(list(c.values()))) if c else 0.0


def score_task(orig, gen, t, bars, drum):
    if gen.resolution != orig.resolution:                # the model decodes at its own ticks per beat
        gen = gen.resample(orig.resolution)
    gt, ge = notes(orig, t, bars), notes(gen, t, bars)
    g = grid(orig)
    m = {"gt_notes": len(gt), "gen_notes": len(ge),
         "density_logratio": float(np.log((len(ge) + 1) / (len(gt) + 1))),
         "onset_sim": cos(onset_hist(gt, orig), onset_hist(ge, orig)),
         "f1": f1(gt, ge, g),
         "poly_gt": polyphony(gt, g), "poly_gen": polyphony(ge, g),
         "vel_gt": float(np.mean([n.velocity for _, n in gt])) if gt else None,
         "vel_gen": float(np.mean([n.velocity for _, n in ge])) if ge else None,
         "vel_sd_gen": float(np.std([n.velocity for _, n in ge])) if ge else None,
         "vel_sd_gt": float(np.std([n.velocity for _, n in gt])) if gt else None,
         "delta_nonzero_gen": float(np.mean([n.delta != 0 for _, n in ge])) if ge else None}
    if not drum:
        ks = key_set(orig, t, bars)
        m.update(pc_sim=cos(pc_hist(gt), pc_hist(ge)),
                 key_fit_gen=float(np.mean([n.pitch % 12 in ks for _, n in ge])) if ge else None,
                 key_fit_gt=float(np.mean([n.pitch % 12 in ks for _, n in gt])) if gt else None,
                 pitch_mean_err=abs(np.mean([n.pitch for _, n in gt]) - np.mean([n.pitch for _, n in ge])) if gt and ge else None)
    else:
        kit = lambda ns: Counter(n.pitch for _, n in ns)
        m.update(kit_sim=cos(np.array([kit(gt)[p] for p in range(128)], float), np.array([kit(ge)[p] for p in range(128)], float)))
    return m


# ---------------------------------------------------------------- run

def request(score, t, bars, ar, dim, bps, seed):
    return GenerationRequest(
        tracks=[TrackPrompt(id=i, bars=list(bars) if i == t else [], autoregressive=ar and i == t) for i in range(len(score.tracks))],
        config=InferenceConfig(model_dim=dim, bars_per_step=bps, tracks_per_step=1, temperature=1.0, seed=seed,
                               max_attempts=3, novelty_check=False, silence_check=True, mask_mode="attention"),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pieces", type=int, default=64)
    ap.add_argument("--midi", type=int, default=12, help="pieces whose generations are saved as MIDI")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "midi", a.model), exist_ok=True)
    t0 = time.time()
    if "=" in a.model:                                   # name=path: a local checkpoint
        a.model, ckpt = a.model.split("=", 1)
        eng = InferenceEngine.from_checkpoint(os.path.expandvars(ckpt))
    else:
        eng = InferenceEngine.from_pretrained(a.model)
    dims = json.loads(eng._tokenizer._vocab.config().to_json()).get("num_bars_map") or []
    print(a.model, "loaded in %.1fs, num_bars_map %s" % (time.time() - t0, dims), flush=True)
    pieces = load_pieces(a.data, a.pieces)
    print(len(pieces), "pieces", flush=True)
    path = os.path.join(a.out, a.model + ".jsonl")
    done = set()
    if os.path.exists(path):
        done = {(r["piece"], r["task"]) for r in map(json.loads, open(path))}
    with open(path, "a") as out:
        for pi, p in enumerate(pieces):
            for k, (name, t, bars, ar, dim, bps) in enumerate(tasks(p["score"], "16" if 16 in dims else "")):
                if (p["id"], name) in done:
                    continue
                rec = {"model": a.model, "piece": p["id"], "task": name, "track": t, "drums": p["score"].tracks[t].track_type == "drum",
                       "instrument": p["score"].tracks[t].instrument, "n_tracks": len(p["score"].tracks)}
                seed = 1000 * pi + k
                t1 = time.time()
                try:
                    sess = eng.session(p["score"], request(p["score"], t, bars, ar, dim, bps, seed))
                    gen = sess.run()
                    rec.update(ok=True, s=time.time() - t1, tokens=sess.gen_count, truncated=bool(sess.truncated),
                               ctx=getattr(sess, "context_len", None), **score_task(p["score"], gen, t, bars, rec["drums"]))
                    if pi < a.midi:
                        gen.to_midi(os.path.join(a.out, "midi", a.model, "%02d_%s_%s.mid" % (pi, p["id"], name)))
                        if not os.path.exists(os.path.join(a.out, "midi", "%02d_%s_original.mid" % (pi, p["id"]))):
                            p["score"].to_midi(os.path.join(a.out, "midi", "%02d_%s_original.mid" % (pi, p["id"])))
                except Exception as e:
                    rec.update(ok=False, s=time.time() - t1, error=str(e)[:300])
                    traceback.print_exc()
                out.write(json.dumps(rec) + "\n"); out.flush()
            print("piece %d/%d %.0fs" % (pi + 1, len(pieces), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
