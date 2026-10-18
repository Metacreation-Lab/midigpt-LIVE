#!/usr/bin/env python3
"""
Render the README art in the device's own style (the Carbon panel of tools/render_ui.py):

  docs/images/title.png   the title: the Metacreation mark and the MIDI-GPT wordmark engraved in the
                          carbon panel, exactly as on the device, with "FOR ABLETON LIVE" under it
  docs/images/hero.png    a screenshot of the device in Live, on a plain monitor facing the camera,
                          on the panel's carbon background

  python3 tools/render_readme_art.py title [--fields <title.npz>] [--blender <title.npy>]
  python3 tools/render_readme_art.py hero <screenshot.png>

The title can be path-traced: --fields dumps its heightfield and materials for tools/video/blender_panel_assets.py,
and --blender takes that render (linear, h x w x 3) in place of the canvas's own shading, at the same exposure.
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frontend_assets as FA  # noqa: E402
import render_ui as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images")
S = R.S
TH = FA.THEMES["carbon"]


def carbon():
    st = dict(R.STYLES["cockpit"])
    R.use_palette(st)
    R.P.update(TH["render"])
    return st


def mask(w_pt, h_pt, draw):
    up = 4
    m = Image.new("L", (int(w_pt * S * up), int(h_pt * S * up)), 0)
    draw(ImageDraw.Draw(m), up)
    return np.asarray(m.resize((int(w_pt * S), int(h_pt * S)), Image.LANCZOS), np.float32) / 255.0


def spaced(d, x, y, s, fnt, fill, spacing):
    """Letter-spaced text with its left edge at x, vertically centred on y (px)."""
    for ch in s:
        d.text((x, y), ch, font=fnt, fill=fill, anchor="lm")
        x += d.textlength(ch, font=fnt) + spacing
    return x


# ------------------------------------------------------------------ title
def title(fields=None, blender=None):
    st = carbon()
    W, H = 1000, 220                          # pt (2x px)
    cap, stroke, gap = 40, 6.0, 15.5            # the device's wordmark proportions (TITLE: cap 11, stroke 2, gap 4.6), scaled
    mark_h = 104
    zero = ImageDraw.Draw(Image.new("L", (4, 4)))
    word_w = R.wordmark(zero, 0, 0, 1, cap, stroke, gap)
    mark_w = 105.63 * mark_h / 137.32
    x0 = (W - (mark_w + 32 + word_w)) / 2
    my = (H - mark_h) / 2
    wx = x0 + mark_w + 32
    wy = H / 2 - cap / 2 - 12

    c = R.Canvas(W * S, H * S, R.P["base"], R.MATTE)
    sc = mark_h / 137.32
    m = mask(mark_w + 4, mark_h + 4, lambda d, up: [d.polygon([((px * sc + 2) * S * up, (py * sc + 2) * S * up) for (px, py) in p], fill=255)
                                                    for p in R.LOGO_POLYS])
    inlay = np.zeros((H * S, W * S), np.float32)   # where the engraving is: kept at the device's brightness
    R.engrave_mask(c, m, int(round((x0 - 2) * S)), int(round((my - 2) * S)), depth=3.0)
    ix, iy = int(round((x0 - 2) * S)), int(round((my - 2) * S))
    inlay[iy:iy + m.shape[0], ix:ix + m.shape[1]] = np.maximum(inlay[iy:iy + m.shape[0], ix:ix + m.shape[1]], m)
    m = mask(word_w + 6, cap + 6, lambda d, up: R.wordmark(d, 3, 3, S * up, cap, stroke, gap))
    R.engrave_mask(c, m, int(round((wx - 3) * S)), int(round((wy - 3) * S)), depth=2.6)
    ix, iy = int(round((wx - 3) * S)), int(round((wy - 3) * S))
    inlay[iy:iy + m.shape[0], ix:ix + m.shape[1]] = np.maximum(inlay[iy:iy + m.shape[0], ix:ix + m.shape[1]], m)
    rgb = c.shade(st)
    if fields:                                    # for Blender: the same fields the panel assets use
        np.savez_compressed(fields, hf=c.hf, alb=(c.alb * c.grain[..., None]).astype(np.float32), shin=c.shin, ks=c.ks,
                            metal=c.metal, emis=c.emis)
        print("wrote", fields)
        return
    if blender:                                   # the path-traced panel, matched to the canvas's tone on the flat panel
        ren = np.load(blender)
        lin = lambda v: np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
        flat = (c.hf == 0) & (inlay == 0)
        lum = lambda im: im[..., 0] * 0.3 + im[..., 1] * 0.59 + im[..., 2] * 0.11
        ren = ren * float(np.median(lum(lin(rgb))[flat]) / np.median(lum(ren)[flat]))
        rgb = np.where(ren <= 0.0031308, ren * 12.92, 1.055 * np.power(np.clip(ren, 0, 1), 1 / 2.4) - 0.055)
    # the panel's real tone: the studio lighting lifts the carbon too far for a banner; darken, with a vignette
    yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
    vig = 1.0 - 0.45 * np.clip(np.sqrt(((xx - W * S * 0.5) / (W * S * 0.75)) ** 2 + ((yy - H * S * 0.5) / (H * S * 0.9)) ** 2), 0, 1) ** 1.5
    k = (0.55 + 0.4 * inlay) * vig
    img = Image.fromarray((np.clip(rgb * k[..., None], 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").convert("RGBA")

    # the subtitle, printed like the panel's legends
    d = ImageDraw.Draw(img)
    spaced(d, wx * S + 2, (wy + cap + 24) * S, "FOR ABLETON LIVE", R.font(9), (128, 128, 128, 255), 7.2 * S)

    img.convert("RGB").save(os.path.join(OUT, "title.png"), optimize=True)
    print("wrote docs/images/title.png", img.size)


# ------------------------------------------------------------------ hero
def hero(shot):
    W, H = 2400, 1500
    base = np.array(R.hexc(TH["render"]["base"]))            # the panel colour, as the backdrop
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
    glow = np.clip(1.0 - r, 0, 1) ** 1.6                     # a soft lift behind the monitor
    bg = base[None, None, :] * (0.55 + 0.75 * glow[..., None])
    noise = np.random.default_rng(1).normal(0, 0.004, (H, W, 1))  # a little grain, like the panel's matte finish
    img = Image.fromarray((np.clip(bg + noise, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").convert("RGBA")

    screen = Image.open(shot).convert("RGB")
    sw = 1680
    sh = round(sw * screen.size[1] / screen.size[0])
    bez = 16                                                  # bezel, px
    mw, mh = sw + 2 * bez, sh + 2 * bez
    mx, my = (W - mw) // 2, 120
    neck_w, neck_h = 200, 150
    foot_w, foot_h = 520, 26
    fy = my + mh + neck_h

    # soft shadows: under the monitor and the foot
    sh_l = Image.new("L", (W, H), 0)
    ds = ImageDraw.Draw(sh_l)
    ds.rounded_rectangle([mx + 30, my + 60, mx + mw - 30, my + mh + 50], radius=12, fill=140)
    ds.ellipse([W / 2 - foot_w * 0.62, fy + foot_h - 14, W / 2 + foot_w * 0.62, fy + foot_h + 34], fill=170)
    sh_l = sh_l.filter(ImageFilter.GaussianBlur(38))
    img.paste((0, 0, 0, 255), (0, 0), sh_l)

    d = ImageDraw.Draw(img)
    # stand: a flat neck and foot in the panel's greys, with a top highlight
    knob = R.rgb(TH["render"]["knob"])
    for i in range(neck_w):   # a brushed neck, lit from the left
        t = i / (neck_w - 1)
        v = int(30 + 14 * (1 - abs(t - 0.3) * 1.6))
        d.line([W / 2 - neck_w / 2 + i, my + mh - 10, W / 2 - neck_w / 2 + i, fy + 4], fill=(v, v, v, 255))
    d.rounded_rectangle([W / 2 - foot_w / 2, fy, W / 2 + foot_w / 2, fy + foot_h], radius=10, fill=knob)
    d.line([W / 2 - foot_w / 2 + 10, fy + 1, W / 2 + foot_w / 2 - 10, fy + 1], fill=(62, 62, 62, 255), width=2)

    # monitor: a black slab with a hairline edge highlight, the screenshot inset
    d.rounded_rectangle([mx, my, mx + mw, my + mh], radius=6, fill=R.rgb(TH["render"]["key"]))
    d.rounded_rectangle([mx, my, mx + mw, my + mh], radius=6, outline=(48, 48, 48, 255), width=2)
    d.line([mx + 8, my + 1, mx + mw - 8, my + 1], fill=(78, 78, 78, 255), width=2)
    scr = screen.resize((sw, sh), Image.LANCZOS)
    rmask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(rmask).rounded_rectangle([0, 0, sw - 1, sh - 1], radius=2, fill=255)
    img.paste(scr, (mx + bez, my + bez), rmask)

    img.convert("RGB").save(os.path.join(OUT, "hero.png"), optimize=True)
    print("wrote docs/images/hero.png", (W, H))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1] == "title":
        a = sys.argv[2:]
        title(fields=a[a.index("--fields") + 1] if "--fields" in a else None,
              blender=a[a.index("--blender") + 1] if "--blender" in a else None)
    else:
        hero(sys.argv[2])
