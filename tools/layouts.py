#!/usr/bin/env python3
"""
Layout studies for the device window, built from the settled components
(render_ui's Cockpit style): trench-sunk bays, flare knobs (with a single-knob
min/max range variant), wide-pill LED toggles, LED-slit keys, HUD screens in
padded pockets, and a small HUD readout for generation stats.

  python3 tools/layouts.py <out_dir> [name ...]
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_ui as R  # noqa: E402
import button_studies as B  # noqa: E402

S = R.S
ST = R.STYLES["cockpit"]
HUD = R.HUD
LVL = -0.1 * S
LED = (38, 150, 214)          # accent for knob rings, pointers and toggle LEDs (one setting); solid, no glow


class Layout:
    def __init__(self, name, title, note, w=960, h=640):
        self.name, self.title, self.note, self.w, self.h = name, title, note, w, h
        self.items = []

    def bay(self, x, y, w, h, title=None, sub=None):
        self.items.append(("bay", x, y, w, h, title, sub))

    def screen(self, x, y, w, h, kind="roll"):
        self.items.append(("screen", x, y, w, h, kind))

    def knob(self, cx, cy, r, v, label, rng=None, dim=False, value=None):
        self.items.append(("knob", cx, cy, r, v, label, rng, dim, value))

    def toggle(self, x, y, label, on, w=44, h=16):
        self.items.append(("toggle", x, y, w, h, label, on))

    def key(self, x, y, w, h, label, lit=False, size=8):
        self.items.append(("key", x, y, w, h, label, lit, size))

    def text(self, x, y, s, size=7, col=None, anchor="l"):
        self.items.append(("text", x, y, s, size, col, anchor))

    def steps(self, x, y, n=16, w=13, h=26):
        self.items.append(("steps", x, y, n, w, h))


# ---------------------------------------------------------------- geometry pass
def geometry(L, c):
    R.engrave_logo(c)
    for it in L.items:
        k = it[0]
        if k == "bay":
            _, x, y, w, h, _, _ = it
            c.rrect(x * S, y * S, w * S, h * S, 12 * S, 1.2 * S, 3.0 * S, "trench", R.P["plate"], R.MATTE, 0, sink=True)
    for it in L.items:
        k = it[0]
        if k == "screen":
            _, x, y, w, h, kind = it
            pad, dep = (5, 2.6) if kind == "roll" else (4, 2.2)
            c.rrect((x - pad) * S, (y - pad) * S, (w + 2 * pad) * S, (h + 2 * pad) * S, (8 + pad) * S, dep * S, 0.5 * S, "chamfer",
                    R.P["plate"], R.MATTE, LVL, sink=True)
            c.rrect(x * S, y * S, w * S, h * S, 7 * S, 0.8 * S, 0.6 * S, "round", R.P["screen"], (30, 0.0, 0), LVL - dep * S)
        elif k == "knob":
            _, cx, cy, r, v, *_ = it
            c.knob(cx * S, cy * S, r * S, v, ST, LVL)
        elif k == "toggle":
            _, x, y, w, h, _, on = it
            R.toggle_part(c, x, y, w, h, on, LVL, "apple")
        elif k == "key":
            _, x, y, w, h, _, lit, _ = it
            B.ledslit(c, x, y, w, h, lit)
        elif k == "steps":
            _, x, y, n, w, h = it
            for i in range(n):
                B.ledslit(c, x + i * (w + 3) + (i // 4) * 3, y, w, h, i in (0, 3, 6, 8, 10, 13))


# ---------------------------------------------------------------- runtime layer
class Ov:
    def __init__(self, L):
        self.Q = S * 2
        self.img = Image.new("RGBA", (L.w * self.Q, L.h * self.Q), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.glow = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        self.g = ImageDraw.Draw(self.glow)
        self.cores = []   # LED cores drawn after the glow

    # LED primitives: a wide halo on the glow layer, a bright core on top
    def led_arc(self, box, a0, a1, width):
        self.g.arc(box, a0, a1, fill=LED + (255,), width=int(width * 2.6))
        self.cores.append(("arc", box, a0, a1, width))

    def led_line(self, p0, p1, width):
        self.g.line([p0, p1], fill=LED + (255,), width=int(width * 3.2))
        self.cores.append(("line", p0, p1, width))

    def led_dot(self, cx, cy, r):
        self.g.ellipse([cx - r * 2.6, cy - r * 2.6, cx + r * 2.6, cy + r * 2.6], fill=LED + (255,))
        self.cores.append(("dot", cx, cy, r))

    def flush_leds(self):
        """Solid accent marks, drawn last (no halo: a glow on a lit panel reads as a shadow)."""
        d = self.d
        for c in self.cores:
            if c[0] == "arc":
                _, box, a0, a1, w = c
                d.arc(box, a0, a1, fill=LED + (255,), width=int(w))
            elif c[0] == "line":
                _, p0, p1, w = c
                d.line([p0, p1], fill=LED + (255,), width=int(w))
            else:
                _, cx, cy, r = c
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LED + (255,))

    def txt(self, x, y, s, size, col, anchor="l", spacing=1.0):
        Q, d = self.Q, self.d
        fnt = R.font(size)
        widths = [d.textlength(ch, font=fnt) for ch in s]
        tot = sum(widths) + spacing * Q * (len(s) - 1)
        cx = x * Q - {"l": 0, "m": tot / 2, "r": tot}[anchor]
        for ch, wd in zip(s, widths):
            d.text((cx, y * Q), ch, font=fnt, fill=col, anchor="lm")
            cx += wd + spacing * Q


def hud_roll(o, x, y, w, h):
    """Scaled version of the main HUD piano roll for any screen size."""
    Q, d = o.Q, o.d
    G, C, M, Wt = HUD["green"], HUD["cyan"], HUD["magenta"], HUD["white"]
    lw = max(1, int(0.8 * Q))
    gx, gw = x + 66, w - 66 - 12
    gap, rows = 3, len(R.SCENE)
    top, bottom = y + 20, y + h - 18
    rh = (bottom - top - (rows - 1) * 3) / rows
    bw = (gw - gap * 7) / 8
    for b in range(8):
        bx = gx + b * (bw + gap)
        o.txt(bx + 2, y + 10, "%02d" % (b + 1), 6.5, G + (230,), spacing=0.5)
        d.line([(bx * Q, (y + 14) * Q), (bx * Q, (y + 17) * Q)], fill=G + (200,), width=lw)
    d.line([(gx * Q, (y + 14) * Q), ((gx + gw) * Q, (y + 14) * Q)], fill=G + (90,), width=lw)
    for i, (ab, role, cells, kind) in enumerate(R.SCENE):
        yy = top + i * (rh + 3)
        ign, tgt = role == "I", role == "T"
        a = 0.3 if ign else 1.0
        if tgt:
            d.polygon([((x + 12) * Q, (yy + rh / 2 - 3) * Q), ((x + 17) * Q, (yy + rh / 2) * Q), ((x + 12) * Q, (yy + rh / 2 + 3) * Q)], fill=C + (255,))
        o.txt(x + 22, yy + rh / 2, ab, 7.5 if rh < 22 else 8.5, (C if tgt else Wt) + (int(255 * (1 if tgt else 0.7) * a),), spacing=1)
        for b in range(8):
            k = cells[b]
            bx = gx + b * (bw + gap)
            x0, y0, x1, y1 = bx * Q, yy * Q, (bx + bw) * Q, (yy + rh) * Q
            if k == "E":
                for xx in range(int(x0), int(x1), int(6 * Q)):
                    d.line([(xx, y0), (min(xx + 3 * Q, x1), y0)], fill=G + (int(60 * a),), width=lw)
                    d.line([(xx, y1), (min(xx + 3 * Q, x1), y1)], fill=G + (int(60 * a),), width=lw)
                continue
            gen = k == "G"
            col = M if gen else G
            if gen:
                Lb = 5 * Q
                for (cx_, cy_, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                    d.line([(cx_, cy_), (cx_ + dx * Lb, cy_)], fill=M + (255,), width=int(1.1 * Q))
                    d.line([(cx_, cy_), (cx_, cy_ + dy * Lb)], fill=M + (255,), width=int(1.1 * Q))
            else:
                d.rectangle([x0, y0, x1, y1], outline=G + (int(70 * a),), width=lw)
            for (nx, nl, npitch) in R.notes_for(ab, kind, b):
                X0 = bx + 3 + nx * (bw - 6)
                X1 = X0 + max(2, nl * (bw - 6))
                Y0 = yy + rh - 4 - npitch * (rh - 8)
                d.rectangle([X0 * Q, (Y0 - 0.9) * Q, X1 * Q, (Y0 + 0.9) * Q], fill=col + (int(255 * (1 if gen else 0.6) * a),))
    o.txt(x + 12, y + h - 9, "TGT BASS LEAD", 6.5, C + (220,), spacing=1)
    o.txt(x + w - 12, y + h - 9, "LINK 410MS", 6.5, G + (220,), anchor="r", spacing=1)


def hud_stats(o, x, y, w, h):
    """The generation readout: context use, speed, time, seed, streamed notes."""
    Q, d = o.Q, o.d
    G, C, M, A = HUD["green"], HUD["cyan"], HUD["magenta"], HUD["amber"]
    lw = max(1, int(0.8 * Q))
    o.txt(x + 8, y + 10, "CTX", 6.5, G + (230,), spacing=0.8)
    n, used = 24, 0.9
    bx0, bw_ = x + 30, (w - 30 - 66) / 24
    for i in range(n):
        lit = i / n < used
        d.rectangle([(bx0 + i * bw_) * Q, (y + 7) * Q, (bx0 + i * bw_ + bw_ - 1.2) * Q, (y + 13) * Q],
                    fill=(A if i / n > 0.8 and lit else G) + ((255,) if lit else (40,)))
    o.txt(x + w - 8, y + 10, "1843/2048", 6.5, G + (230,), anchor="r", spacing=0.5)
    rows = [("TOK/S", "42.6", C), ("TIME", "2.31S", C), ("NOTES", "128", M)] if h < 60 else \
           [("TOK/S", "42.6", C), ("TIME", "2.31S", C), ("NOTES", "128", M), ("SEED", "41529", G), ("ATT", "1/3", G), ("STATUS", "DONE", G)]
    cols = 3
    cw = (w - 16) / cols
    for i, (k, v, col) in enumerate(rows):
        cx = x + 8 + (i % cols) * cw
        cy = y + 25 + (i // cols) * 16
        o.txt(cx, cy, k, 5.8, col + (150,), spacing=0.6)
        o.txt(cx + cw - 6, cy, v, 7.5, col + (255,), anchor="r", spacing=0.4)
    d.line([((x + 6) * Q, (y + 17) * Q), ((x + w - 6) * Q, (y + 17) * Q)], fill=G + (50,), width=lw)


def overlay(L, base):
    o = Ov(L)
    Q, d = o.Q, o.d
    ink, lab = R.rgb(R.P["ink"]), R.rgb(R.P["label"])
    o.txt(48, 21, "MIDI-GPT", 13, ink, spacing=2.4)
    for it in L.items:
        k = it[0]
        if k == "bay" and it[5]:
            _, x, y, w, h, title, sub = it
            o.txt(x + 14, y + 14, title, 7.5, lab, spacing=1.6)
            if sub:
                o.txt(x + w - 14, y + 14, sub, 6.5, ink, anchor="r", spacing=1.2)
        elif k == "screen":
            _, x, y, w, h, kind = it
            (hud_roll if kind == "roll" else hud_stats)(o, x, y, w, h)
        elif k == "knob":
            _, cx, cy, r, v, label, rng, dim, value = it
            rr, bw = r * 1.24, r * 0.12
            col = ink if not dim else (190, 195, 202, 255)
            box = [(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q]
            # segmented LED ring: short arc dashes with gaps; lit ones carry the value (or the min..max span)
            nseg = max(11, int(round(r * 0.9)) | 1)
            step = 270 / nseg
            lo_, hi_ = (rng if rng else (0.0, v))
            for j in range(nseg):
                a0 = 135 + j * step + step * 0.18
                a1 = 135 + (j + 1) * step - step * 0.18
                mid = (j + 0.5) / nseg
                lit = (not dim) and (lo_ - 0.5 / nseg) <= mid <= (hi_ + 0.5 / nseg) and not (not rng and v < 0.004)
                if lit:
                    o.led_arc(box, a0, a1, bw * Q)
                else:
                    d.arc(box, a0, a1, fill=(0, 0, 0, 30), width=int(bw * Q))
            if dim:
                pass
            elif rng:   # range knob: two LED marks on the cap at min and max
                lo, hi = rng
                for vv, wd in ((lo, 0.05), (hi, 0.07)):
                    a = math.radians(-135 + 270 * vv)
                    p0 = (cx + r * 0.46 * math.sin(a), cy - r * 0.46 * math.cos(a))
                    p1 = (cx + r * 0.74 * math.sin(a), cy - r * 0.74 * math.cos(a))
                    o.led_line((p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q), max(1.2, r * wd) * Q)
            else:
                a = math.radians(-135 + 270 * v)
                p0 = (cx + r * 0.42 * math.sin(a), cy - r * 0.42 * math.cos(a))
                p1 = (cx + r * 0.72 * math.sin(a), cy - r * 0.72 * math.cos(a))
                o.led_line((p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q), max(1.6, r * 0.085) * Q)
            ly = cy + rr + bw / 2 + 9
            o.txt(cx, ly, label, 6.8 if r < 20 else 7.2, (84, 90, 102, 255) if not dim else (170, 176, 184, 255), anchor="m", spacing=1.0)
            if value:
                o.txt(cx, ly + 10, value, 6.2, ink if not dim else (190, 195, 202, 255), anchor="m", spacing=0.6)
        elif k == "toggle":
            _, x, y, w, h, label, on = it
            tw = w * 0.76
            lx = (x + w - tw + 2 + tw / 2) if on else (x - 2 + tw / 2)
            if on:
                o.led_dot(lx * Q, (y + h / 2) * Q, 2.0 * Q)
            else:
                d.ellipse([(lx - 2) * Q, (y + h / 2 - 2) * Q, (lx + 2) * Q, (y + h / 2 + 2) * Q], fill=(205, 210, 217, 255))
            o.txt(x + w / 2, y - 9, label, 6.5, lab, anchor="m", spacing=0.9)
        elif k == "key":
            _, x, y, w, h, label, lit, size = it

            def stext(x_, y_, s_, size_, col_, anchor="mm"):
                d.text((x_ * Q, y_ * Q), s_, font=R.font(size_), fill=col_, anchor=anchor)
            if label == "<ret>":
                B.key_overlay(d, stext, Q, "ledslit", x, y, w, h, "", lit)
                mx, my = x + w / 2, y + h / 2 + 2
                ac, lw_ = (150, 155, 164, 255), int(1.5 * Q)
                d.line([((mx + 5) * Q, (my - 5) * Q), ((mx + 5) * Q, (my + 2) * Q), ((mx - 5) * Q, (my + 2) * Q)], fill=ac, width=lw_, joint="curve")
                d.line([((mx - 5) * Q, (my + 2) * Q), ((mx - 2) * Q, (my - 1) * Q)], fill=ac, width=lw_)
                d.line([((mx - 5) * Q, (my + 2) * Q), ((mx - 2) * Q, (my + 5) * Q)], fill=ac, width=lw_)
            else:
                B.key_overlay(d, stext, Q, "ledslit", x, y, w, h, label, lit, size=size)
        elif k == "steps":
            _, x, y, n, w, h = it
            for i in range(n):
                sx = x + i * (w + 3) + (i // 4) * 3
                B.key_overlay(d, lambda *a, **kw: None, Q, "ledslit", sx, y, w, h, "", i in (0, 3, 6, 8, 10, 13))
                beat = i % 4 == 0
                d.line([((sx + w / 2) * Q, (y + h + 3) * Q), ((sx + w / 2) * Q, (y + h + (7 if beat else 5)) * Q)], fill=lab, width=max(1, int((1.1 if beat else 0.8) * Q)))
                if beat:
                    o.txt(sx + w / 2, y + h + 13, str(i // 4 + 1), 6.5, lab, anchor="m", spacing=0)
        elif k == "text":
            _, x, y, s, size, col, anchor = it
            o.txt(x, y, s, size, col or lab, anchor=anchor, spacing=0.9)
    o.flush_leds()
    ov = o.img.resize((L.w * S, L.h * S), Image.LANCZOS)
    out = base.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


def render(L, out_dir):
    R.use_palette(ST)
    c = R.Canvas(L.w * S, L.h * S, R.P["base"], R.MATTE)
    geometry(L, c)
    base = Image.fromarray((c.shade(ST) * 255 + 0.5).astype(np.uint8), "RGB")
    img = overlay(L, base)
    path = os.path.join(out_dir, "layout_%s.jpg" % L.name)
    img.save(path, quality=92, subsampling=0)
    return path


# ---------------------------------------------------------------- shared groups
def top_keys(L, labels=("EXTRAS", "ENGINE", "SETUP")):
    x = L.w - 16 - len(labels) * 76 + 6
    for i, lab in enumerate(labels):
        L.key(x + i * 76, 9, 70, 22, lab, lab == "TRACK", 7.5)


def takes(L, x, y, s=40, gap=6):
    L.key(x, y, s, s, "<ret>", False)
    for i in range(4):
        L.key(x + (i + 1) * (s + gap), y, s, s, str(i + 1), i == 0, 12)


# ---------------------------------------------------------------- the five layouts
def layout_console():
    L = Layout("console", "A  Console", "the current panel, reorganised: track | sample | output, extras strip")
    top_keys(L, ("ENGINE", "SETUP"))
    L.screen(12, 44, 936, 206)
    # TRACK
    L.bay(12, 264, 372, 252, "TRACK", "BASS · MELODIC")
    L.toggle(40, 304, "IGNORE", 0)
    L.toggle(104, 304, "AUTO", 0)
    L.knob(70, 382, 26, 0.3, "POLY", rng=(0.1, 0.3), value="1–3")
    L.knob(186, 382, 26, 0.5, "LENGTH", rng=(0.25, 0.55), value="1/16–1/4")
    L.knob(302, 382, 26, 0.45, "TEMP", value="0.90")
    for i, (lab, v, val) in enumerate((("KEY", 0.2, "D"), ("RANGE", 0.4, "24"), ("SILENCE", 0.1, "1"), ("PCS", 0.55, "7"))):
        L.knob(52 + i * 90, 470, 14, v, lab, value=val)
    L.text(370 - 14, 305, "DENS ON DRUMS", 5.8, anchor="r")
    # SAMPLE
    L.bay(394, 264, 290, 252, "SAMPLE", "ALL TARGETS")
    for i, (lab, v) in enumerate((("TEMP", 0.5), ("TOP-P", 0.95), ("TOP-K", 0.0))):
        L.knob(444 + i * 95, 340, 22, v, lab)
    for i, (lab, v) in enumerate((("ESC", 0.25), ("TAKES", 0.4), ("SEED", 0.6))):
        L.knob(444 + i * 95, 420, 15, v, lab)
    for i, (lab, on) in enumerate((("NOVELTY", 1), ("SILENCE", 1), ("SHUFFLE", 0))):
        L.toggle(420 + i * 95, 490, lab, on)
    # OUTPUT
    L.bay(694, 264, 254, 252, "OUTPUT")
    takes(L, 710, 290, 38, 6)
    L.screen(712, 348, 218, 66, "stats")
    L.key(710, 432, 64, 64, "KEEP", False, 8)
    L.key(782, 432, 150, 64, "GENERATE", False, 11)
    # EXTRAS
    L.bay(12, 528, 936, 100, "EXTRAS", "PITCH MASK · RHYTHM · REMIX")
    L.toggle(36, 576, "SCALE", 1)
    L.knob(120, 578, 13, 0.18, "ROOT")
    L.knob(180, 578, 13, 0.42, "MODE")
    L.knob(244, 578, 13, 0.4, "REGISTER", rng=(0.25, 0.6))
    L.steps(300, 560)
    L.toggle(620, 576, "RHYTHM", 1)
    L.knob(700, 578, 13, 0.8, "STRENGTH")
    L.toggle(770, 576, "REMIX", 0)
    L.knob(850, 578, 13, 0.5, "AMOUNT")
    L.toggle(896, 576, "P+D", 0, w=36)
    return L


def layout_strips():
    L = Layout("strips", "B  Channel strips", "a mixer: every track's controls visible at once; master section on the right")
    top_keys(L, ("EXTRAS", "ENGINE", "SETUP"))
    L.screen(12, 44, 936, 150)
    tracks = [("PNO", "MEL", 0, 0, (0.3, 0.6), (0.2, 0.5)), ("BASS", "MEL", 1, 0, (0.1, 0.2), (0.3, 0.55)), ("DRUM", "DRM", 0, 0, None, None),
              ("PAD", "MEL", 0, 1, (0.4, 0.7), (0.5, 0.8)), ("LEAD", "MEL", 1, 0, (0.1, 0.1), (0.15, 0.4)), ("STR", "MEL", 0, 0, (0.3, 0.6), (0.5, 0.9))]
    for i, (name, kind, tgt, ign, poly, ln) in enumerate(tracks):
        x = 12 + i * 103
        L.bay(x, 206, 97, 310, name, kind)
        L.key(x + 12, 230, 73, 20, "TARGET", bool(tgt), 6.5)
        L.toggle(x + 14, 276, "IGN", ign, w=30, h=12)
        L.toggle(x + 54, 276, "AUTO", 0, w=30, h=12)
        if kind == "DRM":
            L.knob(x + 48, 336, 19, 0.6, "DENSITY", value="6")
            L.knob(x + 48, 420, 19, 0.0, "—", dim=True)
        else:
            L.knob(x + 48, 336, 19, poly[1], "POLY", rng=poly)
            L.knob(x + 48, 420, 19, ln[1], "LENGTH", rng=ln)
        L.knob(x + 48, 486, 11, 0.45, "TEMP")
    L.bay(632, 206, 316, 310, "MASTER", "SAMPLING")
    for i, (lab, v) in enumerate((("TEMP", 0.5), ("TOP-P", 0.95), ("TOP-K", 0.0))):
        L.knob(684 + i * 106, 280, 22, v, lab)
    for i, (lab, v) in enumerate((("ESC", 0.25), ("TAKES", 0.4), ("SEED", 0.6))):
        L.knob(684 + i * 106, 372, 16, v, lab)
    for i, (lab, on) in enumerate((("NOVELTY", 1), ("SILENCE", 1), ("SHUFFLE", 0))):
        L.toggle(662 + i * 106, 456, lab, on)
    L.bay(12, 528, 936, 100)
    takes(L, 30, 550, 56, 8)
    L.screen(366, 548, 300, 62, "stats")
    L.key(684, 548, 70, 62, "KEEP", False, 8.5)
    L.key(764, 548, 166, 62, "GENERATE", False, 11)
    return L


def layout_cluster():
    L = Layout("cluster", "C  Instrument cluster", "the screen in the middle like a car cluster; track left, sampling right")
    top_keys(L, ("ENGINE", "SETUP"))
    L.bay(12, 44, 214, 472, "TRACK", "BASS")
    L.toggle(34, 82, "IGNORE", 0)
    L.toggle(132, 82, "AUTO", 0)
    L.knob(119, 168, 34, 0.3, "POLY", rng=(0.1, 0.3), value="1–3")
    L.knob(119, 300, 34, 0.5, "LENGTH", rng=(0.25, 0.55), value="1/16–1/4")
    L.knob(66, 432, 16, 0.45, "TEMP")
    L.knob(172, 432, 16, 0.4, "RANGE")
    L.screen(244, 49, 472, 300)
    L.bay(238, 366, 484, 150, "EXTRAS", "SCALE · REMIX")
    L.toggle(262, 410, "SCALE", 1)
    L.knob(352, 418, 15, 0.18, "ROOT")
    L.knob(416, 418, 15, 0.42, "MODE")
    L.knob(480, 418, 15, 0.4, "REGISTER", rng=(0.25, 0.6))
    L.toggle(548, 410, "REMIX", 0)
    L.knob(640, 418, 15, 0.5, "AMOUNT")
    L.steps(262, 466, 16, 11, 22)
    L.text(262 + 16 * 14 + 12 + 8, 478, "RHYTHM 1/16", 6.5)
    L.bay(734, 44, 214, 472, "SAMPLE")
    L.knob(841, 150, 36, 0.5, "TEMP", value="1.00")
    L.knob(790, 270, 18, 0.95, "TOP-P")
    L.knob(892, 270, 18, 0.0, "TOP-K")
    L.knob(790, 352, 14, 0.25, "ESC")
    L.knob(892, 352, 14, 0.4, "TAKES")
    for i, (lab, on) in enumerate((("NOVELTY", 1), ("SILENCE", 1), ("SHUFFLE", 0))):
        L.toggle(752 + i * 64, 454, lab, on, w=40, h=14)
    L.bay(12, 528, 936, 100)
    takes(L, 30, 550, 56, 8)
    L.screen(366, 548, 300, 62, "stats")
    L.key(684, 548, 70, 62, "KEEP", False, 8.5)
    L.key(764, 548, 166, 62, "GENERATE", False, 11)
    return L


def layout_rack():
    L = Layout("rack", "D  Rack", "stacked 1U modules, everything visible, no drawers (engine included)")
    top_keys(L, ("EXTRAS", "SETUP"))
    L.screen(12, 44, 936, 160)
    rows = [
        ("TRACK", "BASS · MELODIC", [("POLY", 0.3, (0.1, 0.3)), ("LENGTH", 0.5, (0.25, 0.55)), ("TEMP", 0.45, None), ("KEY", 0.2, None),
                                        ("RANGE", 0.4, None), ("SILENCE", 0.1, None), ("PCS", 0.55, None)], [("IGNORE", 0), ("AUTO", 0)]),
        ("SAMPLE", "ALL TARGETS", [("TEMP", 0.5, None), ("TOP-P", 0.95, None), ("TOP-K", 0.0, None), ("ESC", 0.25, None), ("TAKES", 0.4, None),
                                   ("SEED", 0.6, None), ("ATTEMPTS", 0.3, None)], [("NOVELTY", 1), ("SILENCE", 1), ("SHUFFLE", 0)]),
        ("ENGINE", "YELLOW MEDIUM", [("CONTEXT", 0.3, None), ("BARS/STEP", 0.2, None), ("TRK/STEP", 0.2, None), ("POLY LIM", 0.0, None),
                                     ("DENS LIM", 0.0, None), ("MASK P", 0.0, None), ("MASK K", 0.0, None)], [("VELOCITY", 1), ("MICRO", 0)]),
    ]
    y = 216
    for (title, sub, knobs, toggles) in rows:
        L.bay(12, y, 936, 98, title, sub)
        for i, (lab, v, rng) in enumerate(knobs):
            L.knob(60 + i * 84, y + 54, 17, v, lab, rng=rng)
        for i, (lab, on) in enumerate(toggles):
            L.toggle(680 + i * 88, y + 54, lab, on)
        y += 104
    L.bay(12, 528, 936, 100)
    takes(L, 30, 550, 56, 8)
    L.screen(366, 548, 300, 62, "stats")
    L.key(684, 548, 70, 62, "KEEP", False, 8.5)
    L.key(764, 548, 166, 62, "GENERATE", False, 11)
    return L


def layout_pages():
    L = Layout("pages", "E  Paged", "hardware-synth style: page keys switch one bank of eight knobs")
    top_keys(L, ("SETUP",))
    L.screen(12, 44, 936, 250)
    for i, lab in enumerate(("TRACK", "SAMPLE", "EXTRAS", "ENGINE")):
        L.key(14 + i * 112, 308, 104, 30, lab, i == 0, 8)
    L.toggle(500, 323, "IGNORE", 0)
    L.toggle(580, 323, "AUTO", 0)
    L.text(948 - 14, 323, "BASS · MELODIC · PAGE 1/4", 6.8, R.rgb(R.P["ink"]), anchor="r")
    L.bay(12, 350, 936, 166)
    bank = [("POLY", 0.3, (0.1, 0.3), "1–3"), ("LENGTH", 0.5, (0.25, 0.55), "1/16–1/4"), ("TEMP", 0.45, None, "0.90"), ("KEY", 0.2, None, "D"),
            ("RANGE", 0.4, None, "24"), ("SILENCE", 0.1, None, "1"), ("PCS", 0.55, None, "7"), ("DENSITY", 0.0, None, "DRUMS")]
    for i, (lab, v, rng, val) in enumerate(bank):
        L.knob(70 + i * 117, 426, 28, v, lab, rng=rng, dim=lab == "DENSITY", value=val)
    L.bay(12, 528, 936, 100)
    takes(L, 30, 550, 56, 8)
    L.screen(366, 548, 300, 62, "stats")
    L.key(684, 548, 70, 62, "KEEP", False, 8.5)
    L.key(764, 548, 166, 62, "GENERATE", False, 11)
    return L


ALL = {"console": layout_console, "strips": layout_strips, "cluster": layout_cluster, "rack": layout_rack, "pages": layout_pages}


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for n in sys.argv[2:] or list(ALL):
        print(render(ALL[n](), out))
