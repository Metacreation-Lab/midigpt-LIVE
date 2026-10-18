#!/usr/bin/env python3
"""
Turn the Blender renders of the panel assets (tools/video/blender_panel_assets.py) into the PNGs the device loads,
exactly as tools/export_panel_assets.py writes its own: same names, sizes and sprite pads, sprites' shadows as alpha
(the exporter's with/without formula), and the pre-dimmed _aNN copies.

  python3 tools/video/finish_panel_assets.py <fields_dir> <raw_dir> <out_dir> [--install]

One exposure for every asset: the path-traced plate is scaled to the lo-fi plate's brightness on flat panel (the
colours the panel draws on top were picked against it). --install copies the result over media/panel/midigpt_*.
"""
import os
import shutil
import sys

import numpy as np
from PIL import Image

FIELDS, RAW, OUT = sys.argv[1:4]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
S = 2
DIMS = (28, 50, 55, 62)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def exposure():
    """Scale matching the render to the lo-fi background on the flat panel (height 0, no slope, away from parts)."""
    hf = np.load(os.path.join(FIELDS, "bg_main.npz"))["hf"]
    flat = (hf == 0)
    for _ in range(12):                                  # stay clear of every edge and shadow
        flat[1:-1, 1:-1] &= flat[:-2, 1:-1] & flat[2:, 1:-1] & flat[1:-1, :-2] & flat[1:-1, 2:]
    ren = np.load(os.path.join(RAW, "bg_main.npy"))
    lofi = lin(np.asarray(Image.open(os.path.join(FIELDS, "lofi", "bg_main.png")).convert("RGB"), np.float32) / 255)
    lum = lambda im: im[..., 0] * 0.3 + im[..., 1] * 0.59 + im[..., 2] * 0.11
    return float(np.median(lum(lofi)[flat]) / np.median(lum(ren)[flat]))


def sprite(f, a, b):
    """The exporter's frontend_assets.sprite(): the part where it rises, elsewhere the darkening as black alpha."""
    lum = lambda im: im[..., 0] * 0.3 + im[..., 1] * 0.59 + im[..., 2] * 0.11
    part = np.clip((f["a_hf"] - f["b_hf"]) / (0.5 * S), 0, 1)
    shade_ = np.clip(1 - lum(a) / np.maximum(lum(b), 1e-4), 0, 1)
    alpha = part + (1 - part) * shade_
    hh, ww = alpha.shape
    fy = np.minimum(np.arange(hh), np.arange(hh)[::-1])[:, None] / (10.0 * S)
    fx = np.minimum(np.arange(ww), np.arange(ww)[::-1])[None, :] / (10.0 * S)
    alpha = alpha * np.clip(np.minimum(fx, fy), 0, 1) ** 1.5 * (1 - part) + part
    rgb = a * part[..., None]
    out = np.dstack([np.where(alpha[..., None] > 1e-4, rgb / np.maximum(alpha[..., None], 1e-4), 0), alpha])
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def main():
    os.makedirs(OUT, exist_ok=True)
    k = exposure()
    print("exposure x%.3f" % k)
    names = sorted(f[:-4] for f in os.listdir(FIELDS) if f.endswith(".npz"))
    for name in names:
        f = np.load(os.path.join(FIELDS, name + ".npz"))
        if "hf" in f:
            im = Image.fromarray((srgb(np.load(os.path.join(RAW, name + ".npy")) * k) * 255 + 0.5).astype(np.uint8), "RGB")
            im.save(os.path.join(OUT, "midigpt_%s.png" % name), optimize=True)
            continue
        a, b = (srgb(np.load(os.path.join(RAW, "%s_%s.npy" % (name, p))) * k) for p in "ab")
        im = sprite(f, a, b)
        im.save(os.path.join(OUT, "midigpt_%s.png" % name), optimize=True)
        for d in DIMS:                                   # pre-dimmed copies for disabled parts (midigpt_panel.js DIMS)
            dm = im.copy()
            dm.putalpha(dm.getchannel("A").point(lambda v, d=d: int(v * d / 100 + 0.5)))
            dm.save(os.path.join(OUT, "midigpt_%s_a%d.png" % (name, d)), optimize=True)
    print(len(os.listdir(OUT)), "files in", OUT)
    if "--install" in sys.argv:
        for fn in os.listdir(OUT):
            shutil.copy(os.path.join(OUT, fn), os.path.join(ROOT, "media", "panel", fn))
        print("installed into media/panel")


if __name__ == "__main__":
    main()
