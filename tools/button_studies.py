#!/usr/bin/env python3
"""
Button studies: ten push-button designs rendered with render_ui's 2.5D renderer
on one sheet. Each cell shows a square key off/on, a wide key off/on and a row of
small step keys, so form and lit state can be compared side by side.

  python3 tools/button_studies.py <out.jpg>
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_ui as R  # noqa: E402

S = R.S
CW, CH, COLS, ROWS = 292, 210, 5, 2
SW, SH = CW * COLS, CH * ROWS
PANEL = "#E7E9EC"
WHITE, OFFWHITE, DARK, METAL, GLASS = "#F7F8F9", "#EEEFF1", "#2C2F35", "#C3C8CF", "#14171C"
LIGHT = dict(shadow=dict(off=(3, 7), blur=7, k=0.04, max=0.42), light=dict(blur=7, k=0.015, max=0.3))


def sdf_rr(x, y, w, h, r):
    return lambda X, Y: R.sd_rrect(X, Y, (x + w / 2) * S, (y + h / 2) * S, w / 2 * S, h / 2 * S, r * S)


# ---------------------------------------------------------------- the ten designs: geometry(c, x, y, w, h, lit)
def silicone(c, x, y, w, h, lit):
    cx, cy, hw, hh = (x + w / 2) * S, (y + h / 2) * S, w / 2 * S, h / 2 * S
    pillow = lambda X, Y, ins: 1.4 * S * (1 - np.clip(np.abs(X - cx) / hw, 0, 1) ** 4) * (1 - np.clip(np.abs(Y - cy) / hh, 0, 1) ** 4)
    c.rrect(x * S, y * S, w * S, h * S, 7 * S, 2.6 * S, 2.6 * S, "soft", "#F1F2F3" if lit else "#E4E6E9",
            (12, 0.05, 0), 0, top=pillow, emis=("#FFFFFF", 0.22) if lit else None)


def keycap(c, x, y, w, h, lit):
    cx, hw = (x + w / 2) * S, w / 2 * S
    dish = lambda X, Y, ins: -0.9 * S * (1 - np.clip(np.abs(X - cx) / hw, 0, 1) ** 2) * np.clip(ins / (3 * S), 0, 1)
    c.rrect(x * S, y * S, w * S, h * S, 4 * S, 5.5 * S, 3.2 * S, "chamfer", WHITE, (30, 0.16, 0), 0, top=dish)


def opdisc(c, x, y, w, h, lit):
    r = min(w, h) / 2
    c.rrect(x * S, y * S, w * S, h * S, r * S, (2.0 if lit else 4.2) * S, 1.2 * S, "round", WHITE, (30, 0.16, 0), 0)


def ringlit(c, x, y, w, h, lit):
    r = min(w, h) / 2
    c.rrect(x * S, y * S, w * S, h * S, r * S, 2.2 * S, 1.0 * S, "round", METAL, R.ALU, 0)
    c.rrect((x + 4) * S, (y + 4) * S, (w - 8) * S, (h - 8) * S, (r - 4) * S, 0.8 * S, 0.5 * S, "round", "#D8DCE1", R.ALU, 2.2 * S, sink=True)


def ledslit(c, x, y, w, h, lit):
    c.rrect(x * S, y * S, w * S, h * S, 3.5 * S, 3.4 * S, 1.2 * S, "round", DARK, (40, 0.25, 0), 0)


def latch(c, x, y, w, h, lit):
    c.rrect((x - 1.5) * S, (y - 1.5) * S, (w + 3) * S, (h + 3) * S, 2.5 * S, 3.5 * S, 0.6 * S, "chamfer", "#D9DDE2", R.MATTE, 0, sink=True)
    c.rrect(x * S, y * S, w * S, h * S, 1.5 * S, (1.2 if lit else 3.0) * S, 0.8 * S, "round", WHITE, (30, 0.14, 0), -3.5 * S + 3.5 * S)


def arcade(c, x, y, w, h, lit):
    r = min(w, h) / 2
    c.rrect(x * S, y * S, w * S, h * S, r * S, 1.6 * S, 1.2 * S, "round", "#3A3E45", (60, 0.35, 0), 0)
    m = min(w, h) * 0.13
    cx, cy, hw, hh = (x + w / 2) * S, (y + h / 2) * S, (w / 2 - m) * S, (h / 2 - m) * S
    dome = lambda X, Y, ins: 1.8 * S * np.clip(1 - ((X - cx) / hw) ** 2 * (0 if w > h * 1.5 else 1) - ((Y - cy) / hh) ** 2, 0, 1)
    c.rrect((x + m) * S, (y + m) * S, (w - 2 * m) * S, (h - 2 * m) * S, (r - m) * S, 2.6 * S, 1.6 * S, "round",
            "#FFFFFF" if lit else OFFWHITE, (110, 0.55, 0), 1.6 * S, top=dome, emis=("#FFFFFF", 0.25) if lit else None)


def glass(c, x, y, w, h, lit):
    c.rrect(x * S, y * S, w * S, h * S, 5 * S, 0.6 * S, 0.4 * S, "round", GLASS, (160, 0.6, 0), 0, sink=True)


def softpill(c, x, y, w, h, lit):
    r = min(w, h) / 2
    if lit:
        c.rrect(x * S, y * S, w * S, h * S, r * S, 1.6 * S, min(w, h) * 0.3 * S, "soft", "#E2E5E9", R.MATTE, 0, sink=True)
    else:
        c.rrect(x * S, y * S, w * S, h * S, r * S, 3.2 * S, min(w, h) * 0.4 * S, "soft", WHITE, (30, 0.12, 0), 0)


def shutter(c, x, y, w, h, lit):
    r = min(w, h) / 2
    c.rrect(x * S, y * S, w * S, h * S, r * S, 4.0 * S, 1.4 * S, "chamfer", "#CDD2D8", R.ALU, 0, sink=True)
    m = min(w, h) * 0.16
    cx, cy = (x + w / 2) * S, (y + h / 2) * S
    dome = lambda X, Y, ins: 0.8 * S * np.clip(ins / (min(w, h) * 0.3 * S), 0, 1)
    c.rrect((x + m) * S, (y + m) * S, (w - 2 * m) * S, (h - 2 * m) * S, (r - m) * S, (2.6 if lit else 3.6) * S, 1.6 * S, "round",
            WHITE, (40, 0.2, 0), -4.0 * S, top=dome)


DESIGNS = [
    ("silicone", "1  Silicone pad", "MPC / Push: soft rubber, lit from inside", silicone),
    ("keycap", "2  Sculpted keycap", "mechanical keyboard: tapered walls, dished top", keycap),
    ("opdisc", "3  Round cap", "TE OP-1: white cylinders, pressed sits lower", opdisc),
    ("ringlit", "4  Ring-lit metal", "industrial push button: flat metal, LED ring", ringlit),
    ("ledslit", "5  LED-slit cap", "Elektron / Moog: dark cap, a lit slot on top", ledslit),
    ("latch", "6  Latching keys", "Braun radio piano keys: latched key stays down", latch),
    ("arcade", "7  Arcade dome", "Sanwa: gloss dome in a dark bezel, glows", arcade),
    ("glass", "8  Glass touch", "flush glass field, legend lights", glass),
    ("softpill", "9  Soft pill", "Apple: raised pill, pressed becomes a dent", softpill),
    ("shutter", "10 Shutter well", "camera shutter: cap in a machined well", shutter),
]


def cell_items(cx0, cy0):
    """(x, y, w, h, label, lit) for one cell: square off/on, wide off/on, eight steps."""
    out = [(cx0 + 18, cy0 + 34, 46, 46, "A", 0), (cx0 + 76, cy0 + 34, 46, 46, "A", 1),
           (cx0 + 140, cy0 + 30, 134, 26, "KEEP", 0), (cx0 + 140, cy0 + 64, 134, 26, "KEEP", 1)]
    for i in range(8):
        out.append((cx0 + 18 + i * 18 + (i // 4) * 4, cy0 + 104, 14, 28, "", i in (0, 3, 6)))
    out.append((cx0 + 186, cy0 + 100, 88, 36, "GENERATE", 0))
    return out


def key_overlay(d, text, Q, key, x, y, w, h, lab, lit, size=None):
    """Runtime layer for one key: legend, LED, glow. Shared by the sheet and the panel renderer."""
    ink, white = (34, 38, 46, 255), (246, 248, 250, 255)
    dark_face = key in ("ledslit", "glass")
    col = white if dark_face else ink
    if not lit and dark_face:
        col = (150, 155, 164, 255)
    mx, my = x + w / 2, y + h / 2
    if key == "silicone" and lit:
        d.rounded_rectangle([(x - 2) * Q, (y - 2) * Q, (x + w + 2) * Q, (y + h + 2) * Q], radius=9 * Q, outline=(255, 255, 255, 140), width=int(2 * Q))
    if key == "keycap" and lit:
        d.ellipse([(x + 5) * Q, (y + 5) * Q, (x + 9) * Q, (y + 9) * Q], fill=ink)
    if key == "opdisc" and lit:
        rr = min(w, h) / 2 + 3
        d.rounded_rectangle([(mx - w / 2 - 3) * Q, (my - h / 2 - 3) * Q, (mx + w / 2 + 3) * Q, (my + h / 2 + 3) * Q], radius=rr * Q, outline=ink, width=int(1.2 * Q))
    if key == "ringlit":
        rr = min(w, h) / 2 - 2
        box = [(x + 2) * Q, (y + 2) * Q, (x + w - 2) * Q, (y + h - 2) * Q]
        d.rounded_rectangle(box, radius=rr * Q, outline=(255, 255, 255, 230) if lit else (120, 126, 136, 160), width=int(1.4 * Q))
    if key == "ledslit":
        sw_ = min(18, w * 0.4)
        bar = [(mx - sw_ / 2) * Q, (y + 4) * Q, (mx + sw_ / 2) * Q, (y + 6) * Q] if h > 20 else [(mx - 3) * Q, (y + 4) * Q, (mx + 3) * Q, (y + 6) * Q]
        if lit:
            d.rounded_rectangle([bar[0] - 2 * Q, bar[1] - 2 * Q, bar[2] + 2 * Q, bar[3] + 2 * Q], radius=2 * Q, fill=(255, 255, 255, 60))
        d.rounded_rectangle(bar, radius=Q, fill=(250, 250, 250, 255) if lit else (20, 22, 26, 255))
        my += 2
    if key == "arcade" and lit:
        rr = min(w, h) / 2 + 3
        d.rounded_rectangle([(x - 3) * Q, (y - 3) * Q, (x + w + 3) * Q, (y + h + 3) * Q], radius=rr * Q, outline=(255, 255, 255, 120), width=int(2.4 * Q))
    if key == "glass" and lit:
        d.rounded_rectangle([(x + 1.5) * Q, (y + 1.5) * Q, (x + w - 1.5) * Q, (y + h - 1.5) * Q], radius=4 * Q, outline=(255, 255, 255, 110), width=int(1.2 * Q))
    if key == "shutter" and lit:
        d.ellipse([(mx - 2) * Q, (y + 6) * Q, (mx + 2) * Q, (y + 10) * Q], fill=ink)
    if key == "latch" and lit:
        d.rectangle([(x + 3) * Q, (y + h - 3) * Q, (x + w - 3) * Q, (y + h - 2) * Q], fill=ink)
    if lab:
        size = size or (12 if lab == "A" else 7.5)
        if key == "glass" and lit:
            text(mx, my, lab, size, (255, 255, 255, 90))
        text(mx, my + (1 if key == "softpill" and lit else 0), lab, size, col)


def render(out):
    c = R.Canvas(SW * S, SH * S, PANEL, R.MATTE)
    for i, (key, title, sub, fn) in enumerate(DESIGNS):
        cx0, cy0 = (i % COLS) * CW, (i // COLS) * CH
        for (x, y, w, h, lab, lit) in cell_items(cx0, cy0):
            fn(c, x, y, w, h, lit)
    img = Image.fromarray((c.shade(LIGHT) * 255 + 0.5).astype(np.uint8), "RGB").convert("RGBA")

    Q = S * 2
    ov = Image.new("RGBA", (SW * Q, SH * Q), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ink, grey, white = (34, 38, 46, 255), (120, 126, 136, 255), (246, 248, 250, 255)

    def text(x, y, s, size, col, anchor="mm"):
        d.text((x * Q, y * Q), s, font=R.font(size), fill=col, anchor=anchor)

    for i, (key, title, sub, fn) in enumerate(DESIGNS):
        cx0, cy0 = (i % COLS) * CW, (i // COLS) * CH
        text(cx0 + 18, cy0 + 162, title, 9, ink, "lm")
        d.text(((cx0 + 18) * Q, (cy0 + 178) * Q), sub, font=R.font(6.8, bold=False), fill=grey, anchor="lm")
        text(cx0 + 41, cy0 + 24, "OFF", 6, grey)
        text(cx0 + 99, cy0 + 24, "ON", 6, grey)
        for (x, y, w, h, lab, lit) in cell_items(cx0, cy0):
            key_overlay(d, text, Q, key, x, y, w, h, lab, lit)
    ov = ov.resize((SW * S, SH * S), Image.LANCZOS)
    img.alpha_composite(ov)
    img.convert("RGB").save(out, quality=92, subsampling=0)


if __name__ == "__main__":
    render(sys.argv[1])
