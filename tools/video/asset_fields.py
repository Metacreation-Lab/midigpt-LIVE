#!/usr/bin/env python3
"""
Dump the panel assets' geometry and materials for Blender (tools/video/blender_panel_assets.py): runs the exporter
(tools/frontend_assets.py, Carbon) unchanged, but records every canvas it shades, so Blender gets the exact same
heightfields, sizes and sprite pads, and only the lighting changes.

  python3 tools/video/asset_fields.py <out_dir>

Writes <out_dir>/<asset>.npz per asset: for a background one field set; for a sprite two (with the part, "a", and
without it, "b", as the exporter's shadow-to-alpha needs). Fields (px, h x w): hf (height, px), alb (linear RGB,
grain applied), shin, ks, metal, emis (linear RGB).
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, TOOLS)
import frontend_assets as FA  # noqa: E402
import render_ui as R  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
captured = []
_shade = R.Canvas.shade


def shade(self, st):
    captured.append(dict(hf=self.hf.copy(), alb=(self.alb * self.grain[..., None]).astype(np.float32), shin=self.shin.copy(),
                         ks=self.ks.copy(), metal=self.metal.copy(), emis=self.emis.copy()))
    return _shade(self, st)


_save = Image.Image.save


def save(self, fp, *a, **k):
    name = os.path.splitext(os.path.basename(str(fp)))[0]
    if len(captured) == 1:
        np.savez_compressed(os.path.join(out, name), **captured[0])
    else:
        np.savez_compressed(os.path.join(out, name), **{"a_" + kk: v for kk, v in captured[0].items()},
                            **{"b_" + kk: v for kk, v in captured[1].items()})
    captured.clear()
    return _save(self, fp, *a, **k)


R.Canvas.shade = shade
Image.Image.save = save
FA.export_theme("carbon", os.path.join(out, "lofi"))     # the current lo-fi renders, for comparison
print("fields for", len([f for f in os.listdir(out) if f.endswith(".npz")]), "assets in", out)
