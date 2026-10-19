#!/usr/bin/env python3
"""
Which context to drop when a step doesn't fit: compare drop policies by how well the model still predicts the real
bars (teacher-forced NLL), at the same token budgets.

  python3 tools/eval/context_drop_eval.py --model yellow_medium|<name>=<checkpoint> (--data <test parquet dir> | --midi <glob>)
      --out <dir> [--pieces 96] [--dim 8] [--shard 0 --shards 1]

For each piece and task (one target track, infill or AR continuation, inside one window of --dim bars):
  - encode the step with every context track (full) and with none (none); their NLLs bound what dropping can cost;
  - for each budget (drop at least f of the context tokens, f in 0.25 / 0.5 / 0.75; and, when the full step doesn't
    fit the model, the real budget), each policy drops units in its order until the prompt fits, and the real target
    bars are scored under the model.
Writes <out>/<model>_d<dim>[_s<shard>].jsonl, one line per (piece, task, policy, budget). Summarise with
context_drop_report.py.

Policies (units are whole context tracks unless E_*):
  random_k        random order (3 seeds)
  big_first       most tokens first
  A, A_nocost     GM-program roles, relevance table; drop lowest relevance per token (A_nocost: lowest relevance)
  B               roles from the notes (register, polyphony, drum kit) instead of the program
  C               redundancy: drop the track most similar to another kept one, per token
  ABC             B weighted down by redundancy, per token
  D_<q>_<l>_<a>   attention of the target's prompt tokens (q=tgt) or the last prompt token (q=last), summed over
                  layers l=all/top/bot, per context track; a=mass drops the least attended first, a=dens divides by
                  the track's tokens
  DxB             D_tgt_all_mass times B's relevance
  D_iter          D_tgt_all_mass, recomputed after every drop
  D_kl            leave-one-out KL of the next-token distribution at the end of the prompt (no ground truth)
  E_uniform       bars far from the targets first, every track alike (a shorter window, in tokens)
  E_B             bars, weighted by B and distance to the targets, per token
  E_D             bars, by attention of the target's prompt tokens
  oracle_loo      leave-one-out NLL of the real bars per token (uses the ground truth: an upper reference)
  oracle_greedy   greedy on the real bars' NLL, recomputed after every drop (upper reference)
  dim_half        infill only: no drops, the window halved around the targets (what step-down does today)
"""
import argparse, copy, glob, json, os, random, sys, time, traceback

import numpy as np
import torch

import midigpt._core as C
from midigpt._converters import to_cpp
from midigpt._types import Score
from midigpt.inference.engine import InferenceEngine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_eval import SEG, busiest, load_pieces  # noqa: E402

FRACS = (0.25, 0.5, 0.75)
TT = C.TokenType


# ---------------------------------------------------------------- roles and relevance

def gm_role(track):
    if track.track_type == "drum":
        return "drums"
    p = track.instrument
    if 32 <= p <= 39:
        return "bass"
    if p <= 7 or 16 <= p <= 31 or 40 <= p <= 55 or 88 <= p <= 95:
        return "harmony"
    if 56 <= p <= 87 or 104 <= p <= 111 or 8 <= p <= 15:
        return "lead"
    return "other"


def content_role(track, res):
    ns = [n for b in track.bars for n in b.notes]
    if not ns:
        return "other"
    if track.track_type == "drum":
        c = np.bincount([n.pitch for n in ns], minlength=128)
        core = c[[35, 36, 37, 38, 39, 40]].sum()
        hats = c[[42, 44, 46, 49, 51, 52, 53, 55, 57, 59]].sum()
        return "kit" if core >= hats and core > 0.25 * len(ns) else ("hats" if hats > 0.5 * len(ns) else "perc")
    g = max(1, res // 4)
    onsets = {}
    for bi, b in enumerate(track.bars):
        for n in b.notes:
            onsets[(bi, round(n.onset_ticks / g))] = onsets.get((bi, round(n.onset_ticks / g)), 0) + 1
    poly = np.mean(list(onsets.values()))
    pitch = np.mean([n.pitch for n in ns])
    if pitch < 50 and poly < 1.3:
        return "bass"
    if poly >= 1.8:
        return "harmony"
    return "lead"


REL = {   # REL[target role][context role]: how much the context helps predict the target
    "melodic": {"bass": .9, "harmony": .8, "lead": .6, "drums": .5, "kit": .6, "hats": .35, "perc": .35, "other": .3},
    "bass":    {"bass": .6, "harmony": .8, "lead": .5, "drums": .9, "kit": .95, "hats": .5, "perc": .5, "other": .3},
    "drums":   {"bass": .8, "harmony": .4, "lead": .3, "drums": .9, "kit": .9, "hats": .7, "perc": .6, "other": .3},
}


def rel(target_role, ctx_role, same_family):
    tr = "drums" if target_role in ("drums", "kit", "hats", "perc") else ("bass" if target_role == "bass" else "melodic")
    return REL[tr][ctx_role] + (0.1 if same_family else 0.0)


def onset_grid(track, res):
    g = max(1, res // 4)
    v = np.zeros(len(track.bars) * 16)
    for bi, b in enumerate(track.bars):
        for n in b.notes:
            v[min(len(v) - 1, bi * 16 + int(n.onset_ticks // g) % 16)] = 1
    return v


def pc_vec(track):
    v = np.zeros(12)
    for b in track.bars:
        for n in b.notes:
            v[n.pitch % 12] += 1
    return v


def cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return 0.0 if na == 0 or nb == 0 else float(a @ b / na / nb)


# ---------------------------------------------------------------- one step: encoding and scoring

class Case:
    """One window (D bars), one target track, infill or AR continuation; analyzer attributes computed once."""

    def __init__(self, eng, score16, start, D, target, bars, ar):
        self.eng, self.D, self.target, self.bars, self.ar = eng, D, target, sorted(bars), ar
        tok = eng._tokenizer
        self.vocab, self.enc = tok._vocab, tok._encoder
        s = Score(tracks=[], resolution=score16.resolution, tempo=score16.tempo)
        for t in score16.tracks:
            s.tracks.append(type(t)(bars=copy.deepcopy(t.bars[start:start + D]), instrument=t.instrument, track_type=t.track_type))
        an = eng._analyzer
        if an is not None:
            for ti, tr in enumerate(s.tracks):
                a = dict(tr.attributes)
                a.update(an.compute_track_tokens(s, ti))
                for bi in range(len(tr.bars)):
                    for k, v in an.compute_bar_tokens(s, ti, bi).items():
                        a[f"bar_{k}_{bi}"] = v
                tr.attributes = a
        self.raw = s
        self.base = tok.normalize_input(s)
        self.n = len(self.base.tracks)
        self.ctx = [i for i in range(self.n) if i != target]
        self.fill_start = self.vocab.encode_val(TT.FillInStart, 0)
        self.cache = {}

    def encode(self, drop=(), hide=()):
        """(prompt, continuation, hidden spans, track of each prompt token, bar of each prompt token)."""
        key = (tuple(sorted(drop)), tuple(sorted(hide)))
        if key in self.cache:
            return self.cache[key]
        s = copy.deepcopy(self.base)
        for t, b in hide:
            s.tracks[t].bars[b].future = True
        keep = [i for i in range(self.n) if i not in drop]
        order = [i for i in keep if not (self.ar and i == self.target)] + ([self.target] if self.ar else [])
        s.tracks = [s.tracks[i] for i in order]
        ti = order.index(self.target)
        opts = C.EncodeOptions()
        opts.window_bars = self.D
        opts.use_span_masks = True
        if not self.ar:
            opts.multi_fill = {(ti, b) for b in self.bars}
        cs = to_cpp(s)
        full = self.enc.encode_full(cs, opts)
        toks, spans = list(full.tokens), [tuple(x) for x in full.hidden_spans]
        while toks and self.vocab.get_type(toks[-1]) == TT.PieceEnd:
            toks.pop()
        if self.ar:
            opts.partial_encode_track_index = ti
            opts.partial_encode_track_bars = self.bars[0]
            prompt = list(self.enc.encode_full(cs, opts).tokens)
            while prompt and self.vocab.get_type(prompt[-1]) in (TT.PieceEnd, TT.TrackEnd):
                prompt.pop()
            assert toks[:len(prompt)] == prompt, "AR prompt is not a prefix of the full encoding"
            split = len(prompt)
            last_bar = self.bars[-1]
            assert last_bar == self.D - 1, "AR targets run to the end of the window"
        else:
            split = toks.index(self.fill_start) + 1
        prompt, cont = toks[:split], toks[split:]
        spans = [(a, min(b, split)) for a, b in spans if a < split]
        trk, bar, k, cur, cb = [], [], -1, -1, -1
        for x in prompt:
            ty = self.vocab.get_type(x)
            if ty == TT.Track:
                k += 1; cur = order[k]; cb = -1
            elif ty == TT.Bar:
                cb += 1
            elif ty == TT.FillInStart:
                cur, cb = -2, -1
            trk.append(cur); bar.append(cb)
        out = (prompt, cont, spans, np.array(trk), np.array(bar))
        self.cache[key] = out
        return out

    def plen(self, drop=(), hide=()):
        return len(self.encode(drop, hide)[0])


class Scorer:
    def __init__(self, model):
        self.m = model
        self.dev = next(model.parameters()).device
        self.max_ctx = model.max_context()
        self.cache = {}

    @torch.no_grad()
    def nll(self, case, drop=(), hide=()):
        key = (id(case), tuple(sorted(drop)), tuple(sorted(hide)))
        if key in self.cache:
            return self.cache[key]
        prompt, cont, spans, _, _ = case.encode(drop, hide)
        seq = prompt + cont
        if len(seq) > self.max_ctx:
            return None
        ids = torch.tensor([seq], device=self.dev)
        km = None
        if spans:
            km = torch.ones(len(seq), dtype=torch.bool, device=self.dev)
            for a, b in spans:
                km[a:b] = False
        logits, _ = self.m(ids, key_mask=km)
        lp = torch.log_softmax(logits[0, len(prompt) - 1:-1].float(), -1)
        v = -float(lp.gather(1, torch.tensor(cont, device=self.dev)[:, None]).sum())
        self.cache[key] = v
        return v

    @torch.no_grad()
    def attention(self, case, drop=()):
        """Attention mass on each prompt token, from (tgt) the target's prompt tokens plus the last token and
        (last) the last token alone; per layer: dict q -> (L, T) numpy."""
        prompt, _, spans, trk, _ = case.encode(drop)
        assert not spans
        ids = torch.tensor([prompt], device=self.dev)
        tr = self.m.transformer
        x = tr.wte(ids) + tr.wpe(torch.arange(len(prompt), device=self.dev)[None])
        q_tgt = torch.tensor(np.where((trk == case.target) | (np.arange(len(prompt)) == len(prompt) - 1))[0], device=self.dev)
        out = {"tgt": [], "last": []}
        for blk in tr.h:
            x, _, w = blk(x, past_kv=None, return_attn_weights=True)
            w = w[0].mean(0)                                  # (T, T), heads averaged
            out["tgt"].append((w[q_tgt].sum(0) / len(q_tgt)).float().cpu().numpy())
            out["last"].append(w[-1].float().cpu().numpy())
            del w
        return {k: np.stack(v) for k, v in out.items()}

    @torch.no_grad()
    def last_dist(self, case, drop=()):
        prompt = case.encode(drop)[0]
        logits, _ = self.m(torch.tensor([prompt], device=self.dev))
        return torch.log_softmax(logits[0, -1].float(), -1)


# ---------------------------------------------------------------- policies: an order of units to drop

def track_costs(case):
    full = case.plen()
    return {t: full - case.plen(drop=(t,)) for t in case.ctx}


def bar_costs(case):
    full = case.plen()
    return {(t, b): full - case.plen(hide=((t, b),)) for t in case.ctx for b in range(case.D)}


def static_order(units, keep_value):
    """Drop the lowest keep value first (ties: unit order)."""
    return sorted(units, key=lambda u: (keep_value[u], str(u)))


def layer_slice(L, which):
    return {"all": slice(0, L), "top": slice(L // 2, L), "bot": slice(0, L // 2)}[which]


def policies(case, scorer, rng_seed):
    """name -> list of units in drop order (track ids, or (track, bar) for E_*)."""
    res = case.base.resolution
    tracks = case.raw.tracks
    cost = track_costs(case)
    tgt = tracks[case.target]
    roles_a = {t: gm_role(tracks[t]) for t in range(case.n)}
    roles_b = {t: content_role(tracks[t], res) for t in range(case.n)}
    fam = lambda t: tracks[t].instrument // 8 if tracks[t].track_type != "drum" else -1
    rel_a = {t: rel(roles_a[case.target], roles_a[t], fam(t) == fam(case.target)) for t in case.ctx}
    rel_b = {t: rel(roles_b[case.target], roles_b[t], fam(t) == fam(case.target)) for t in case.ctx}
    c = {t: max(1, cost[t]) for t in case.ctx}
    out = {}
    for k in range(3):
        r = list(case.ctx); random.Random(rng_seed * 7 + k).shuffle(r); out[f"random_{k}"] = r
    out["big_first"] = static_order(case.ctx, {t: -cost[t] for t in case.ctx})
    out["A"] = static_order(case.ctx, {t: rel_a[t] / c[t] for t in case.ctx})
    out["A_nocost"] = static_order(case.ctx, {t: rel_a[t] for t in case.ctx})
    out["B"] = static_order(case.ctx, {t: rel_b[t] / c[t] for t in case.ctx})

    feats = {t: (onset_grid(tracks[t], res), pc_vec(tracks[t])) for t in case.ctx}

    def redundancy(t, kept):
        best = 0.0
        for u in kept:
            if u == t or (tracks[u].track_type == "drum") != (tracks[t].track_type == "drum"):
                continue
            s = cos(feats[t][0], feats[u][0])
            if tracks[t].track_type != "drum":
                s = 0.5 * s + 0.5 * cos(feats[t][1], feats[u][1])
            best = max(best, s)
        return best

    def iterative(value):
        kept, order = list(case.ctx), []
        while kept:
            u = min(kept, key=lambda t: (value(t, kept), t))
            order.append(u); kept.remove(u)
        return order

    out["C"] = iterative(lambda t, kept: (1.05 - redundancy(t, kept)) / c[t])
    out["ABC"] = iterative(lambda t, kept: rel_b[t] * (1 - 0.7 * redundancy(t, kept)) / c[t])

    # D: attention from the full prompt (needs the prompt alone to fit the model)
    if case.plen() < scorer.max_ctx:
        trk, bar = case.encode()[3], case.encode()[4]
        att = scorer.attention(case)
        L = att["tgt"].shape[0]
        mass = {}
        for q in ("tgt", "last"):
            for lw in ("all", "top", "bot"):
                a = att[q][layer_slice(L, lw)].sum(0)
                mass[(q, lw)] = {t: float(a[trk == t].sum()) for t in case.ctx}
                out[f"D_{q}_{lw}_mass"] = static_order(case.ctx, mass[(q, lw)])
                out[f"D_{q}_{lw}_dens"] = static_order(case.ctx, {t: mass[(q, lw)][t] / c[t] for t in case.ctx})
        m0 = mass[("tgt", "all")]
        out["DxB"] = static_order(case.ctx, {t: m0[t] * rel_b[t] for t in case.ctx})
        # D_iter: recompute after each drop
        kept, order, dropped = list(case.ctx), [], []
        while kept:
            if len(kept) == 1:
                order.append(kept[0]); break
            a = scorer.attention(case, drop=tuple(dropped))["tgt"].sum(0)
            trk_d = case.encode(tuple(dropped))[3]
            m = {t: float(a[trk_d == t].sum()) for t in kept}
            u = min(kept, key=lambda t: (m[t], t))
            order.append(u); kept.remove(u); dropped.append(u)
        out["D_iter"] = order
        # D_kl: how much the next-token distribution at the end of the prompt moves without each track
        p0 = scorer.last_dist(case)
        kl = {t: float((p0.exp() * (p0 - scorer.last_dist(case, drop=(t,)))).sum()) for t in case.ctx}
        out["D_kl"] = static_order(case.ctx, {t: kl[t] / c[t] for t in case.ctx})
        # E_D: bar units by attention of the target's prompt tokens
        a = att["tgt"].sum(0)
        out["E_D"] = static_order([(t, b) for t in case.ctx for b in range(case.D)],
                                  {(t, b): float(a[(trk == t) & (bar == b)].sum()) for t in case.ctx for b in range(case.D)})

    # E: bars far from the targets first
    bc = bar_costs(case)
    dist = {b: min(abs(b - x) for x in case.bars) for b in range(case.D)}
    units = [(t, b) for t in case.ctx for b in range(case.D)]
    out["E_uniform"] = static_order(units, {(t, b): 1.0 / (1 + dist[b]) - 1e-6 * bc[(t, b)] for t, b in units})
    out["E_B"] = static_order(units, {(t, b): rel_b[t] / (1 + dist[b]) / max(1, bc[(t, b)]) for t, b in units})

    # oracles: the real bars' NLL
    full = scorer.nll(case)
    if full is not None:
        loo = {t: (scorer.nll(case, drop=(t,)) - full) / c[t] for t in case.ctx}
        out["oracle_loo"] = static_order(case.ctx, loo)
        kept, order, dropped = list(case.ctx), [], []
        while kept:
            if len(kept) == 1:
                order.append(kept[0]); break
            base = scorer.nll(case, drop=tuple(dropped))
            u = min(kept, key=lambda t: ((scorer.nll(case, drop=tuple(dropped + [t])) - base) / c[t], t))
            order.append(u); kept.remove(u); dropped.append(u)
        out["oracle_greedy"] = order
    meta = {"roles_gm": roles_a, "roles_notes": roles_b, "costs": cost}
    return out, meta


def apply(case, order, budget):
    """Smallest prefix of the order whose prompt fits the budget: (drop, hide) or None."""
    drop, hide = [], []
    for u in [None] + list(order):
        if u is not None:
            if isinstance(u, tuple):
                hide.append(u)
                t = u[0]
                if sum(1 for x in hide if x[0] == t) == case.D:        # every bar hidden: remove the track
                    hide = [x for x in hide if x[0] != t]; drop.append(t)
            else:
                drop.append(u)
                hide = [x for x in hide if x[0] != u]
        if case.plen(tuple(drop), tuple(hide)) <= budget:
            return tuple(drop), tuple(hide)
    return None


# ---------------------------------------------------------------- tasks and main loop

def tasks(score16, D):
    """(name, target track, target bars (window-local), ar); the window is centred in the 16-bar segment."""
    m0, m1, d0 = busiest(score16, False), busiest(score16, False, 1), busiest(score16, True)
    h = D // 2
    out = [("fill2_mel", m0, [h - 1, h], False), ("fill4_mel2", m1, list(range(h - 2, h + 2)), False),
           ("cont_mel", m0, list(range(h, D)), True)]
    if d0 is not None:
        out += [("fill2_drum", d0, [h - 1, h], False), ("cont_drum", d0, list(range(h, D)), True)]
    return [t for t in out if t[1] is not None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data")
    ap.add_argument("--midi", help="glob of 16-bar MIDI segments instead of --data (local tests)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pieces", type=int, default=96)
    ap.add_argument("--dim", type=int, default=0, help="window in bars (default: the model's largest)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    if "=" in a.model:
        a.model, ckpt = a.model.split("=", 1)
        eng = InferenceEngine.from_checkpoint(os.path.expandvars(ckpt))
    else:
        eng = InferenceEngine.from_pretrained(a.model)
    eng._model.eval()
    dims = json.loads(eng._tokenizer._vocab.config().to_json()).get("num_bars_map") or [8]
    D = a.dim or max(dims)
    scorer = Scorer(eng._model)
    print(a.model, "loaded in %.1fs, dims %s, window %d, context %d" % (time.time() - t0, dims, D, scorer.max_ctx), flush=True)
    if a.midi:
        pieces = [{"id": os.path.basename(p)[:13], "score": Score.from_midi(p)} for p in sorted(glob.glob(a.midi))]
    else:
        pieces = load_pieces(a.data, a.pieces)
    pieces = pieces[a.shard::a.shards]
    suffix = f"_s{a.shard}" if a.shards > 1 else ""
    path = os.path.join(a.out, f"{a.model}_d{D}{suffix}.jsonl")
    done = set()
    if os.path.exists(path):
        done = {(r["piece"], r["task"]) for r in map(json.loads, open(path))}
    start = (SEG - D) // 2
    with open(path, "a") as out:
        for pi, p in enumerate(pieces):
            sc = p["score"]
            if min(len(t.bars) for t in sc.tracks) < start + D:
                continue
            for k, (name, t, bars, ar) in enumerate(tasks(sc, D)):
                if (p["id"], name) in done:
                    continue
                t1 = time.time()
                scorer.cache.clear()
                try:
                    case = Case(eng, sc, start, D, t, bars, ar)
                    full_p, cont = case.plen(), len(case.encode()[1])
                    none_p = case.plen(drop=tuple(case.ctx))
                    if none_p + cont > scorer.max_ctx or full_p == none_p or not cont:
                        continue
                    nll_full, nll_none = scorer.nll(case), scorer.nll(case, drop=tuple(case.ctx))
                    pols, meta = policies(case, scorer, 1000 * (a.shard + a.shards * pi) + k)
                    budgets = [(f"f{f}", full_p - f * (full_p - none_p)) for f in FRACS]
                    if full_p + cont > scorer.max_ctx:
                        budgets.append(("fit", scorer.max_ctx - cont))
                    common = {"model": a.model, "dim": D, "piece": p["id"], "task": name, "ar": ar, "track": t,
                              "drums": case.raw.tracks[t].track_type == "drum", "n_tracks": case.n,
                              "full_prompt": full_p, "none_prompt": none_p, "cont": cont,
                              "nll_full": nll_full, "nll_none": nll_none}
                    rows = []
                    for bname, bud in budgets:
                        for pname, order in pols.items():
                            sel = apply(case, order, bud)
                            if sel is None:
                                continue
                            drop, hide = sel
                            rows.append({**common, "policy": pname, "budget": bname, "budget_tokens": int(bud),
                                         "prompt": case.plen(drop, hide), "dropped": list(drop), "hidden": len(hide),
                                         "nll": scorer.nll(case, drop, hide)})
                    if not ar:                                     # today's step-down: half the window, no drops
                        h = Case(eng, sc, start + D // 4, D // 2, t, [b - D // 4 for b in bars], False)
                        if h.plen() + len(h.encode()[1]) <= scorer.max_ctx:
                            rows.append({**common, "policy": "dim_half", "budget": "dim_half", "budget_tokens": h.plen(),
                                         "prompt": h.plen(), "dropped": [], "hidden": 0, "nll": scorer.nll(h)})
                    rows.append({**common, "policy": "_meta", "budget": "", "meta": {k2: {str(x): y for x, y in v.items()} for k2, v in meta.items()},
                                 "s": time.time() - t1})
                    for r in rows:
                        out.write(json.dumps(r) + "\n")
                    out.flush()
                except Exception as e:
                    traceback.print_exc()
                    out.write(json.dumps({"piece": p["id"], "task": name, "policy": "_error", "error": str(e)[:300]}) + "\n")
                    out.flush()
            print("piece %d/%d %.0fs" % (pi + 1, len(pieces), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
