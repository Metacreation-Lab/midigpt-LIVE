#!/usr/bin/env python3
"""
Background for the MIDI-GPT Instrument tag device (layout C, 112 x 169 pt),
rendered in the main device's cockpit style with the Carbon theme: a screen
pocket for the readout, two key bodies under the family / program menus
(transparent native live.menus sit on top), and the engraved mark + wordmark.

  python3 tools/tag_device_assets.py <out.png>          the tag
  python3 tools/tag_device_assets.py <out.png> strip    the main device's strip
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frontend_assets as FA  # noqa: E402
import render_ui as R  # noqa: E402
import button_studies as B  # noqa: E402

S = R.S
W, H = 112, 169
SCREEN = (8, 8, 96, 62)
MENUS = [(8, 84, 96, 18), (8, 108, 96, 18)]   # family, program
MARK = (8, 145, 12)                             # x, y, height
WORD = dict(x=24, y=148, cap=5.4, stroke=1.1, gap=2.3)


def mask(w_pt, h_pt, draw):
    up = 4
    m = Image.new("L", (int(w_pt * S * up), int(h_pt * S * up)), 0)
    draw(ImageDraw.Draw(m), up)
    return np.asarray(m.resize((int(w_pt * S), int(h_pt * S)), Image.LANCZOS), np.float32) / 255.0


# The main device's strip in Live's device chain (tools/build_panel_device.py): one big key that opens the window.
STRIP = dict(w=96, screen=None, keys=[(10, 10, 76, 118)])


def render(w=W, screen=SCREEN, keys=MENUS, mark=True):
    th = FA.THEMES["carbon"]
    st = dict(R.STYLES["cockpit"])
    st["knob"] = [tuple(list(k[:5]) + [th["knob_mat"]] + [k[6]]) for k in st["knob"]]
    R.use_palette(st)
    R.P.update(th["render"])
    B.DARK = th["render"]["key"]
    c = R.Canvas(w * S, H * S, R.P["base"], R.MATTE)
    if screen:
        FA.screen_pocket(c, *screen)
    for (kx, ky, kw, kh) in keys:
        B.ledslit(c, kx, ky, kw, kh, 0)
    T = dict(WORD)
    if not mark:   # the strip: the mark is on its key, so the wordmark alone, centred
        from PIL import ImageDraw as D
        tw = R.wordmark(D.Draw(Image.new("L", (4, 4))), 0, 0, 1, T["cap"], T["stroke"], T["gap"])
        T["x"] = (w - tw) / 2
    x, y, hgt = MARK
    sc = hgt / 137.32
    m = mask(105.63 * sc + 2, hgt + 2, lambda d, up: [d.polygon([((px * sc + 1) * S * up, (py * sc + 1) * S * up) for (px, py) in p], fill=255)
                                                       for p in R.LOGO_POLYS])
    if mark:
        R.engrave_mask(c, m, int(round((x - 1) * S)), int(round((y - 1) * S)), depth=1.2)
    m = mask(w - T["x"] - 2, T["cap"] + 2, lambda d, up: R.wordmark(d, 1, 1, S * up, T["cap"], T["stroke"], T["gap"]))
    R.engrave_mask(c, m, int(round((T["x"] - 1) * S)), int(round((T["y"] - 1) * S)), depth=1.0)
    img = c.shade(st)
    return Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "strip":
        render(STRIP["w"], STRIP["screen"], STRIP["keys"], mark=False).save(sys.argv[1], optimize=True)
    else:
        render().save(sys.argv[1], optimize=True)
    print("saved", sys.argv[1])
