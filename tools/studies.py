#!/usr/bin/env python3
"""
Control studies on one sheet each, rendered with render_ui's 2.5D renderer:
ten white knobs and ten Apple-like toggles (short travel, big rounded thumb).

  python3 tools/studies.py knobs   <out.jpg>
  python3 tools/studies.py toggles <out.jpg>
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_ui as R  # noqa: E402

S = R.S
PANEL, WHITE, SLOT, SLOT_ON, INK, GREY = "#E7E9EC", "#FBFBFC", "#CDD2D9", "#2A2E36", (34, 38, 46, 255), (120, 126, 136, 255)
LIGHT = dict(light_dir=[-0.10, -0.85, 0.58], shadow=dict(off=(0, 24), blur=16, k=0.10, max=0.70, soft_max=0.58, steps=80), light=None, ao=0.010,
             shadow_mode="ray", exposure=0.84)
SATIN = (30, 0.12, 0)


# ---------------------------------------------------------------- knobs: geometry(c, cx, cy, R) in pixels, plus indicator kind
def disc(c, cx, cy, r, h, w, kind, top=None, level=0.0):
    c.disc(cx, cy, r, h, w, kind, WHITE, SATIN, level, top=top)


def k_puck(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.30 * R_, 0.06 * R_, "round")


def k_flare(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.40 * R_, 0.36 * R_, "flare")


def k_dome(c, cx, cy, R_):
    top = lambda X, Y, ins: 0.10 * R_ * np.clip(1 - (np.hypot(X - cx, Y - cy) / R_) ** 2, 0, 1)
    disc(c, cx, cy, R_, 0.18 * R_, 0.10 * R_, "round", top)


def k_chamfer(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.32 * R_, 0.10 * R_, "chamfer")


def k_tiered(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.10 * R_, 0.05 * R_, "round")
    disc(c, cx, cy, R_ * 0.74, 0.40 * R_, 0.06 * R_, "round")


def k_pebble(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.36 * R_, 0.36 * R_, "round")


def k_dish(c, cx, cy, R_):
    top = lambda X, Y, ins: -0.06 * R_ * np.clip(1 - (np.hypot(X - cx, Y - cy) / (R_ * 0.85)) ** 2, 0, 1)
    disc(c, cx, cy, R_, 0.34 * R_, 0.08 * R_, "round", top)


def k_pillow(c, cx, cy, R_):
    disc(c, cx, cy, R_, 0.30 * R_, 0.55 * R_, "soft")


def k_grip(c, cx, cy, R_):
    top = lambda X, Y, ins: -0.03 * R_ * (0.5 + 0.5 * np.cos(np.arctan2(Y - cy, X - cx) * 40)) * np.clip(1 - ins / (0.18 * R_), 0, 1)
    disc(c, cx, cy, R_, 0.32 * R_, 0.05 * R_, "round", top)


def k_rim(c, cx, cy, R_):
    rr = lambda X, Y: np.hypot(X - cx, Y - cy)
    top = lambda X, Y, ins: -0.05 * R_ * np.clip((R_ * 0.80 - rr(X, Y)) / (0.04 * R_), 0, 1)
    disc(c, cx, cy, R_, 0.32 * R_, 0.06 * R_, "round", top)


KNOBS = [  # key, title, form, indicator, value display
    ("puck", "1  Puck", "short wall, small round edge, flat top", k_puck, "line", "arc"),
    ("flare", "2  Flare", "short wall, then an accelerating rise, flat top", k_flare, "line", "arc"),
    ("dome", "3  Low dome", "almost no wall, gently domed", k_dome, "dot", "arc"),
    ("chamfer", "4  Chamfer", "straight conical side, crisp top", k_chamfer, "line", "ticks"),
    ("tiered", "5  Tiered", "low base disc, smaller puck on top", k_tiered, "line", "arc"),
    ("pebble", "6  Pebble", "fully rounded edge, no flat wall", k_pebble, "dot", "arc"),
    ("dish", "7  Dished", "Braun: round edge, concave top", k_dish, "dot", "ticks"),
    ("pillow", "8  Pillow", "slow S-curve swell, very soft", k_pillow, "line", "arc"),
    ("grip", "9  Fine grip", "flat top, subtle ribbed edge", k_grip, "notch", "arc"),
    ("rim", "10 Rimmed", "flat top inset inside a raised lip", k_rim, "line", "dots"),
]


def knob_sheet(out):
    CW, CH, COLS = 236, 176, 5
    SW, SH = CW * COLS, CH * 2
    c = R.Canvas(SW * S, SH * S, PANEL, R.MATTE)
    spots = []
    for i, k in enumerate(KNOBS):
        x0, y0 = (i % COLS) * CW, (i // COLS) * CH
        for (dx, dy, r, v) in ((70, 70, 32, 0.68), (170, 62, 18, 0.3), (170, 112, 12, 0.85)):
            k[3](c, (x0 + dx) * S, (y0 + dy) * S, r * S)
            spots.append((i, x0 + dx, y0 + dy, r, v))
    img = Image.fromarray((c.shade(LIGHT) * 255 + 0.5).astype(np.uint8), "RGB").convert("RGBA")
    Q = S * 2
    ov = Image.new("RGBA", (SW * Q, SH * Q), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for (i, cx, cy, r, v) in spots:
        ind, disp = KNOBS[i][4], KNOBS[i][5]
        a = math.radians(-135 + 270 * v)
        rr = r + 6
        if disp == "arc":
            d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 135 + 270 * v, fill=INK, width=int(max(1.6, r * 0.08) * Q))
        elif disp == "ticks":
            for j in range(11):
                aa = math.radians(-135 + 27 * j)
                on = j / 10 <= v + 1e-6
                p0 = (cx + (r + 4) * math.sin(aa), cy - (r + 4) * math.cos(aa))
                p1 = (cx + (r + 8) * math.sin(aa), cy - (r + 8) * math.cos(aa))
                d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=INK if on else (34, 38, 46, 60), width=int(1.2 * Q))
        else:
            for j in range(13):
                aa = math.radians(-135 + 22.5 * j)
                on = j / 12 <= v + 1e-6
                px, py = cx + (r + 6) * math.sin(aa), cy - (r + 6) * math.cos(aa)
                d.ellipse([(px - 1.3) * Q, (py - 1.3) * Q, (px + 1.3) * Q, (py + 1.3) * Q], fill=INK if on else (34, 38, 46, 50))
        if ind == "line":
            p0 = (cx + r * 0.38 * math.sin(a), cy - r * 0.38 * math.cos(a))
            p1 = (cx + r * 0.74 * math.sin(a), cy - r * 0.74 * math.cos(a))
            d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=INK, width=int(max(1.4, r * 0.08) * Q))
        elif ind == "dot":
            px, py = cx + r * 0.62 * math.sin(a), cy - r * 0.62 * math.cos(a)
            rd = max(1.3, r * 0.08)
            d.ellipse([(px - rd) * Q, (py - rd) * Q, (px + rd) * Q, (py + rd) * Q], fill=INK)
        else:  # notch at the rim
            p0 = (cx + r * 0.80 * math.sin(a), cy - r * 0.80 * math.cos(a))
            p1 = (cx + r * 0.98 * math.sin(a), cy - r * 0.98 * math.cos(a))
            d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=INK, width=int(max(1.6, r * 0.1) * Q))
    for i, k in enumerate(KNOBS):
        x0, y0 = (i % COLS) * CW, (i // COLS) * CH
        d.text(((x0 + 16) * Q, (y0 + 140) * Q), k[1], font=R.font(9), fill=INK, anchor="lm")
        d.text(((x0 + 16) * Q, (y0 + 156) * Q), k[2], font=R.font(6.8, bold=False), fill=GREY, anchor="lm")
    finish(img, ov, SW, SH, out)


# ---------------------------------------------------------------- toggles: (slot w, slot h, slot depth, slot edge, thumb w, thumb h, thumb r frac, dome, fill_on, extra)
TOGGLES = [
    ("1  Classic", "thumb a bit taller than the slot, short travel", (46, 18, 1.8, 0.4, 30, 22, 0.5, 0.6, 1, None)),
    ("2  Flush", "thumb the slot's height, sits inside it", (46, 20, 2.2, 0.4, 30, 18, 0.5, 0.4, 1, "inset")),
    ("3  Big thumb", "thumb covers most of a tiny slot", (40, 14, 1.6, 0.4, 32, 24, 0.46, 0.7, 1, None)),
    ("4  Squircle", "rounded-rectangle thumb, 35% corners", (46, 18, 1.8, 0.4, 30, 22, 0.35, 0.5, 1, None)),
    ("5  Pillow", "soft domed thumb", (46, 18, 1.8, 0.4, 30, 22, 0.5, 1.6, 1, None)),
    ("6  Grip dots", "flat thumb with two grip dots", (46, 18, 1.8, 0.4, 30, 22, 0.45, 0.2, 1, "dots")),
    ("7  On a groove", "oval thumb riding a thin groove", (44, 5, 1.2, 0.3, 30, 22, 0.5, 0.6, 1, None)),
    ("8  LED thumb", "a dot on the thumb lights when on", (46, 18, 1.8, 0.4, 30, 22, 0.5, 0.6, 0, "led")),
    ("9  Deep slot", "hard, deeper slot; thumb drops into it", (46, 20, 3.4, 0.3, 28, 18, 0.5, 0.5, 1, "inset")),
    ("10 Wide pill", "wide pill thumb, slot peeks at one end", (50, 16, 1.8, 0.4, 38, 22, 0.5, 0.6, 1, None)),
    ("11 Wide pill + LED", "flat crisp-edged thumb, LED dot, slot peeks out", (50, 16, 1.8, 0.4, 38, 22, 0.5, 0.0, 1, "led-crisp")),
]


def toggle_geo(c, x, y, spec, on):
    sw, sh, sd, se, tw, th, rf, dome, fill_on, extra = spec
    cy = y + 14
    c.rrect(x * S, (cy - sh / 2) * S, sw * S, sh * S, sh / 2 * S, sd * S, se * S, "chamfer", SLOT_ON if (on and fill_on) else SLOT, R.MATTE, 0, sink=True)
    travel = sw - tw + (4 if extra != "inset" else -4)
    tx = x + (travel / 2 if extra == "inset" else -2) + (travel if on and extra != "inset" else 0) + (0 if extra != "inset" else (travel / 2 if on else -travel / 2))
    ty = cy - th / 2
    base = -(sd - 0.4) * S if extra == "inset" else 0
    cx_, cy_ = (tx + tw / 2) * S, (ty + th / 2) * S
    top = lambda X, Y, ins: dome * S * np.clip(1 - ((X - cx_) / (tw / 2 * S)) ** 2 - ((Y - cy_) / (th / 2 * S)) ** 2, 0, 1)
    edge = 0.9 if extra == "led-crisp" else min(1.8, th * 0.12)
    c.rrect(tx * S, ty * S, tw * S, th * S, th * rf * S, 3.2 * S, edge * S, "round", WHITE, SATIN, base, top=top)
    return (tx, ty, tw, th)


def toggle_sheet(out):
    CW, CH, COLS, Z = 236, 132, 4, 1.0
    SW, SH = CW * COLS, CH * 3
    c = R.Canvas(SW * S, SH * S, PANEL, R.MATTE)
    marks = []
    for i, (title, sub, spec) in enumerate(TOGGLES):
        x0, y0 = (i % COLS) * CW, (i // COLS) * CH
        for j, on in enumerate((0, 1)):
            t = toggle_geo(c, x0 + 22 + j * 100, y0 + 34, spec, on)
            marks.append((i, on, t))
    img = Image.fromarray((c.shade(LIGHT) * 255 + 0.5).astype(np.uint8), "RGB").convert("RGBA")
    Q = S * 2
    ov = Image.new("RGBA", (SW * Q, SH * Q), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for (i, on, (tx, ty, tw, th)) in marks:
        extra = TOGGLES[i][2][9]
        mx, my = tx + tw / 2, ty + th / 2
        if extra == "dots":
            for dx in (-3, 3):
                d.ellipse([(mx + dx - 1.1) * Q, (my - 1.1) * Q, (mx + dx + 1.1) * Q, (my + 1.1) * Q], fill=(150, 156, 166, 255))
        if extra in ("led", "led-crisp"):
            d.ellipse([(mx - 2) * Q, (my - 2) * Q, (mx + 2) * Q, (my + 2) * Q], fill=INK if on else (200, 205, 212, 255))
    for i, (title, sub, spec) in enumerate(TOGGLES):
        x0, y0 = (i % COLS) * CW, (i // COLS) * CH
        d.text(((x0 + 44) * Q, (y0 + 18) * Q), "OFF", font=R.font(6), fill=GREY, anchor="mm")
        d.text(((x0 + 144) * Q, (y0 + 18) * Q), "ON", font=R.font(6), fill=GREY, anchor="mm")
        d.text(((x0 + 16) * Q, (y0 + 92) * Q), title, font=R.font(9), fill=INK, anchor="lm")
        d.text(((x0 + 16) * Q, (y0 + 108) * Q), sub, font=R.font(6.8, bold=False), fill=GREY, anchor="lm")
    finish(img, ov, SW, SH, out)


def finish(img, ov, SW, SH, out):
    ov = ov.resize((SW * S, SH * S), Image.LANCZOS)
    img.alpha_composite(ov)
    img.convert("RGB").save(out, quality=92, subsampling=0)


if __name__ == "__main__":
    {"knobs": knob_sheet, "toggles": toggle_sheet}[sys.argv[1]](sys.argv[2])
