#!/usr/bin/env python3
"""
Render the MIDI-GPT panel art the way plugin GUIs are usually made: model the
surface in 3D, light it once, and ship the result as images. The static
panel becomes one background render; each knob becomes a filmstrip (one
frame per angle) that the UI script picks a frame from. Only live data
(piano-roll notes, value rings, text) is drawn in code.

There is no 3D package here, so this is a small 2.5D renderer: every part is
a height field built from signed-distance shapes, each with an edge profile
(how the surface rises from the panel: a soft S-curve, a quarter-round, a
chamfer) and a top (flat, domed, dished, knurled). Normals come from the
height field and are lit with a key and a fill light, Blinn-Phong highlights,
ambient occlusion, a soft cast shadow and, for soft-form styles, the matching
light "shadow" on the lit side. Everything renders at 2x for retina.

Styles differ in form only; they share one neutral palette (colour comes later).

  python3 tools/render_ui.py mock <out_dir> [style ...]    full-panel mock-ups (JPEG) + knob strips (PNG)
  python3 tools/render_ui.py list                          style names
  python3 tools/render_ui.py compose <raw.png> <style> <out_dir>   overlay runtime layer on a Blender render
  python3 tools/render_ui.py strip <frames_dir> <out.png>          stitch Blender knob frames into a filmstrip
"""

import math
import os
import sys

import numpy as np
try:  # also imported inside Blender for the layout, where PIL is absent
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

S = 2                       # render scale (retina)
W, H = 960, 640             # window in Max points
FONT_DIR = "/Applications/Ableton Live 11 Suite.app/Contents/App-Resources/Fonts"


def hexc(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def lin(c):
    return np.power(c, 2.2)


def srgb(c):
    return np.power(np.clip(c, 0, 1), 1 / 2.2)


# one neutral palette for every style
P = dict(base="#D8D8D5", plate="#E2E2DF", knob="#ECECEA", key="#E9E9E6", screen="#171717", ink="#2B2B2A",
         label="#8A8A86", lit="#1F1F1F", on_lit="#F4F4F2", metal="#C9C9C6", dark="#3A3A39")

P_NEUTRAL = dict(P)
ORBITAL = dict(base="#E9ECEF", plate="#E6E9ED", knob="#F8F9FA", key="#2B2F38", screen="#1B1F27", ink="#2A2E36",
               label="#6A717E", lit="#2B2F38", on_lit="#EEF0F3", metal="#C9CED6", dark="#262B34", dimple="#B4BDC9")


COCKPIT = dict(base="#E7E9EC", plate="#E2E5E9", knob="#F6F7F9", key="#3A3D43", screen="#061226", ink="#22262E",
               label="#6A717E", lit="#3A3D43", on_lit="#F4F6F8", dark="#22262E", bezel="#3A3D43", face="#1C1E22",
               face_lit="#5A5E66", track="#CDD2D9", track_on="#2A2E36")


def use_palette(st):
    P.clear()
    P.update(P_NEUTRAL)
    P.update(st.get("palette", {}))


# materials: (shininess, specular strength, metal)
MATTE, SATIN, GLOSS, ALU = (10, 0.04, 0), (30, 0.16, 0), (140, 0.5, 0), (50, 0.45, 0.8)


# ---------------------------------------------------------------- edge profiles (t: 0 at the outline, 1 at full height)
def prof(kind, t):
    if kind == "flare":
        # one continuous profile: a short rounded wall up to WALL of the height, levelling off at t = A,
        # then a zero-slope-start exponential rise to full height (C1-smooth, no visible seam)
        A, WALL, K = 0.14, 0.2, 3.4
        t = np.clip(t, 0, 1)
        wall = WALL * np.sqrt(np.clip(1 - (1 - np.clip(t / A, 0, 1)) ** 2, 0, 1))
        u = np.clip((t - A) / (1 - A), 0, 1)
        e = (np.exp(K * u) - 1 - K * u) / (math.exp(K) - 1 - K)
        return np.where(t < A, wall, WALL + (1 - WALL) * e)
    if kind == "trench":
        t = np.maximum(t, 0)
        return np.where(t <= 1, 1.0, np.exp(-(t - 1) * 0.35))
    t = np.clip(t, 0, 1)
    if kind == "soft":       # slow start, slow finish: the surface swells out of the panel
        return t * t * t * (t * (t * 6 - 15) + 10)
    if kind == "exp":        # progressive rise that accelerates, then a soft shoulder
        e = (np.exp(3.2 * t) - 1) / (math.exp(3.2) - 1)
        return e * (1 - 0.35 * (1 - t) ** 2) / 1.0
    if kind == "round":      # quarter-round fillet
        return np.sqrt(np.clip(1 - (1 - t) ** 2, 0, 1))
    if kind == "chamfer":
        return t
    if kind == "trench":     # full depth from the hard outer edge to t = 1, then eases back up exponentially
        return np.where(t <= 1, 1.0, np.exp(-(t - 1) * 0.35))
    raise ValueError(kind)


# ---------------------------------------------------------------- styles
# panel: soft  | flat  | seams | pockets | slab
# knob:  layers of discs (radius x R, height x R, edge width x R, profile, top, material)
STYLES = {
    "softform": dict(
        name="Soft Form", school="neumorphic soft UI · the Sonic Controller mock-up",
        panel="soft", plate_h=2.5, plate_w=16, plate_r=16, screen_depth=4, screen_w=8,
        knob=[(1.22, 0.30, 0.55, "soft", None, SATIN, "knob"), (0.78, 0.62, 0.16, "soft", ("dome", 0.05), SATIN, "knob")],
        pointer=("line", 0.30, 0.66, 0.045), ring="collar",
        key=dict(shape="pill", h=3.5, w=0.55, prof="soft", top=None, lit="press"),
        shadow=dict(off=(4, 7), blur=10, k=0.035, max=0.38), light=dict(blur=10, k=0.03, max=0.55)),
    "braun": dict(
        name="Functional", school="Braun / Dieter Rams · Teenage Engineering",
        panel="flat", screen_depth=3, screen_w=2.5,
        knob=[(1.0, 0.70, 0.07, "round", ("dish", 0.07), MATTE, "knob")],
        pointer=("dot", 0.62, 0.0, 0.085), ring="ticks",
        key=dict(shape="round", h=4, w=0.12, prof="round", top=("dish", 0.12), lit="dot"),
        shadow=dict(off=(2, 5), blur=6, k=0.03, max=0.3), light=None),
    "functional_a": None, "functional_b": None, "functional_c": None,
    "console": dict(
        name="Machined", school="studio console · Elektron, SSL, Neve",
        panel="seams", screen_depth=3, screen_w=1.5,
        knob=[(1.16, 0.14, 0.10, "chamfer", None, ALU, "metal"), (0.92, 0.68, 0.05, "round", ("knurl", 0.025), MATTE, "dark"),
              (0.70, 0.74, 0.04, "chamfer", None, ALU, "metal")],
        pointer=("groove", 0.18, 0.66, 0.035), ring="leds",
        key=dict(shape="square", h=3, w=0.08, prof="round", top=None, lit="led"),
        shadow=dict(off=(2, 5), blur=4, k=0.07, max=0.5), light=None),
    "carved": dict(
        name="Carved", school="milled wells · Push 3, Erica Synths, hardware encoders",
        panel="pockets", plate_h=4, plate_w=4, plate_r=12, screen_depth=4, screen_w=3,
        well=(1.42, 0.30, 0.20), knob=[(1.0, 0.36, 0.42, "soft", ("dome", 0.12), SATIN, "knob")],
        pointer=("line", 0.25, 0.62, 0.05), ring="floor",
        key=dict(shape="well", h=3, w=0.3, prof="soft", top=None, lit="press"),
        shadow=dict(off=(2, 5), blur=6, k=0.05, max=0.45), light=dict(blur=6, k=0.02, max=0.3)),
    "orbital": dict(
        name="Orbital", school="the Orbital Sound white panel",
        panel="pockets", plate_h=1.4, plate_w=5, plate_r=12, screen_depth=3, screen_w=2, palette=ORBITAL,
        well=(1.40, 0.10, 0.32), band=(1.16, 0.12, 0.08),
        knob=[(1.0, 0.46, 0.24, "round", ("dome", 0.02), SATIN, "knob")],
        pointer=("dimple", 0.66, 0.0, 0.10), ring="band", label_pill=True,
        key=dict(shape="dark", h=3.6, w=0.42, prof="soft", top=None, lit="corner", text="on_lit"),
        toggles=True,
        shadow=dict(off=(3, 8), blur=9, k=0.03, max=0.34), light=dict(blur=8, k=0.02, max=0.4)),
    "cockpit": dict(
        name="Cockpit", school="Sonic Controller knobs, Apple toggles, cockpit lit push-buttons",
        panel="pockets", plate_h=1.0, plate_w=4, plate_r=12, screen_depth=1.6, screen_w=1.2, palette=COCKPIT, screen_spec=0.0,
        knob=[(1.0, 0.40, 0.36, "flare", None, SATIN, "knob")],
        collar=(1.24, 0.12, 0.0), pointer=("none", 0, 0, 0), ring="fill", hud=True, trench=(1.2, 3.0), screen_pocket=(5, 2.6),
        key=dict(shape="study", design=os.environ.get("MIDIGPT_KEYS", "ledslit"), h=3.0, w=0.1, prof="round", top=None, lit="study"),
        toggles="apple",
        light_dir=[-0.10, -0.85, 0.58], shadow=dict(off=(0, 24), blur=16, k=0.10, max=0.70, soft_max=0.58, steps=80), light=None, ao=0.010,
        shadow_mode="ray", exposure=0.84, logo=True),
    "monolith": dict(
        name="Monolith", school="one slab · Bang & Olufsen, Teenage Engineering Field",
        panel="slab", screen_depth=2.5, screen_w=1.2,
        knob=[(1.0, 0.10, 0.06, "round", ("dome", 0.04), ALU, "metal")], gap=1.6,
        pointer=("dot", 0.72, 0.0, 0.07), ring="hairline",
        key=dict(shape="flush", h=0.6, w=0.05, prof="round", top=None, lit="glow"),
        shadow=dict(off=(1, 2), blur=2, k=0.08, max=0.35), light=None),
}


# Functional button studies: the Braun panel with three key builds (keycap, calculator, tab)
for _n, _lit in (("functional_a", "press"), ("functional_b", "press"), ("functional_c", "dot")):
    STYLES[_n] = dict(STYLES["braun"], key=dict(STYLES["braun"]["key"], lit=_lit))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, base_col, base_mat=MATTE, grain=0.012, seed=1):
        self.w, self.h = w, h
        self.hf = np.zeros((h, w), np.float32)
        self.alb = np.empty((h, w, 3), np.float32); self.alb[:] = lin(hexc(base_col))
        self.shin = np.full((h, w), base_mat[0], np.float32)
        self.ks = np.full((h, w), base_mat[1], np.float32)
        self.metal = np.full((h, w), base_mat[2], np.float32)
        self.emis = np.zeros((h, w, 3), np.float32)
        rs = np.random.RandomState(seed)
        self.grain = 1 + grain * blur(rs.standard_normal((h, w)).astype(np.float32), 1) * 2.2

    def win(self, x0, y0, x1, y1):
        x0, y0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
        x1, y1 = min(self.w, int(math.ceil(x1))), min(self.h, int(math.ceil(y1)))
        Y, X = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
        return (slice(y0, y1), slice(x0, x1)), X, Y

    def paint(self, sl, cov, col=None, mat=None, emis=None):
        c = cov[..., None]
        if col is not None:
            self.alb[sl] = self.alb[sl] * (1 - c) + lin(hexc(col)) * c
        if mat is not None:
            for arr, v in ((self.shin, mat[0]), (self.ks, mat[1]), (self.metal, mat[2])):
                arr[sl] = arr[sl] * (1 - cov) + v * cov
        if emis is not None:
            self.emis[sl] = self.emis[sl] * (1 - c) + lin(hexc(emis[0])) * emis[1] * c

    def shape(self, sdf_fn, bbox, height, width, kind, col, mat, level, sink=False, top=None, emis=None):
        """Raise (or sink) any SDF shape by `height` over an edge `width` with profile `kind`."""
        sl, X, Y = self.win(*bbox)
        d = sdf_fn(X, Y)
        inside = -d
        p = height * prof(kind, inside / max(width, 1e-3))
        if top is not None:
            p = p + top(X, Y, inside)
        cov = np.clip(0.5 - d, 0, 1)
        if sink:
            self.hf[sl] = np.where(inside > 0, np.minimum(self.hf[sl], level - p), self.hf[sl])
        else:
            self.hf[sl] = np.where(inside > 0, np.maximum(self.hf[sl], level + p), self.hf[sl])
        self.paint(sl, cov, col, mat, emis)

    def rrect(self, x, y, w, h, r, height, width, kind, col, mat, level, sink=False, top=None, emis=None):
        fn = lambda X, Y: sd_rrect(X, Y, x + w / 2, y + h / 2, w / 2, h / 2, r)
        self.shape(fn, (x - 2, y - 2, x + w + 2, y + h + 2), height, width, kind, col, mat, level, sink, top, emis)

    def disc(self, cx, cy, r, height, width, kind, col, mat, level, sink=False, top=None, emis=None):
        fn = lambda X, Y: np.hypot(X - cx, Y - cy) - r
        self.shape(fn, (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), height, width, kind, col, mat, level, sink, top, emis)

    def groove(self, sdf_fn, bbox, width, depth, darken=0.4):
        sl, X, Y = self.win(*bbox)
        g = np.exp(-(sdf_fn(X, Y) / width) ** 2)
        self.hf[sl] -= depth * g
        self.paint(sl, g * darken, "#000000")

    def knob(self, cx, cy, R, value, st, level):
        a = math.radians(-135 + 270 * value)
        for (rm, hm, wm, kind, top, mat, colkey) in st["knob"]:
            r = R * rm
            tf = None
            if top:
                tk, amt = top
                if tk == "dome":
                    tf = (lambda r_=r, amt_=amt: lambda X, Y, ins: amt_ * R * np.clip(1 - (np.hypot(X - cx, Y - cy) / r_) ** 2, 0, 1))()
                elif tk == "dish":
                    tf = (lambda r_=r, amt_=amt: lambda X, Y, ins: -amt_ * R * np.clip(1 - (np.hypot(X - cx, Y - cy) / (r_ * 0.86)) ** 2, 0, 1))()
                elif tk == "knurl":
                    tf = (lambda r_=r, amt_=amt: lambda X, Y, ins: -amt_ * R * (0.5 + 0.5 * np.cos(np.arctan2(Y - cy, X - cx) * 48)) * np.clip(1 - ins / (0.16 * R), 0, 1))()
            self.disc(cx, cy, r, hm * R, wm * R, kind, P[colkey], mat, level, top=tf)
        if st.get("gap"):
            self.groove(lambda X, Y: np.hypot(X - cx, Y - cy) - R - st["gap"] * S, (cx - R - 8, cy - R - 8, cx + R + 8, cy + R + 8), 0.55 * S, 1.0 * S, 0.25)
        # pointer
        kind, u0, u1, hw = st["pointer"]
        if kind == "none":
            return
        sl, X, Y = self.win(cx - R, cy - R, cx + R, cy + R)
        dx, dy = X - cx, Y - cy
        u = dx * math.sin(a) - dy * math.cos(a)
        v = dx * math.cos(a) + dy * math.sin(a)
        if kind == "dot":
            dd = np.hypot(u - u0 * R, v) - hw * R
        else:
            dd = np.hypot(u - np.clip(u, u0 * R, u1 * R), v) - hw * R
        pc = np.clip(0.5 - dd, 0, 1)
        if kind == "dimple":
            dd = np.hypot(u - u0 * R, v)
            dep = np.clip(1 - (dd / (hw * R)) ** 2, 0, 1)
            self.hf[sl] -= 0.12 * R * dep
            self.paint(sl, np.clip(0.5 + hw * R - dd, 0, 1) * 0.55, P.get("dimple", P["label"]))
        elif kind == "groove":
            self.hf[sl] -= 0.9 * S * pc
            self.paint(sl, pc * 0.5, "#000000")
        elif kind == "dot":
            self.hf[sl] -= 0.6 * S * pc
            self.paint(sl, pc, P["ink"], MATTE)
        else:
            self.paint(sl, pc, P["ink"], MATTE)

    def arc_band(self, cx, cy, rr, bw, height, col, level):
        """A raised dark band on a 270-degree arc around a knob, with rounded edges."""
        sl, X, Y = self.win(cx - rr - bw, cy - rr - bw, cx + rr + bw, cy + rr + bw)
        d = np.abs(np.hypot(X - cx, Y - cy) - rr) - bw / 2
        ang = np.degrees(np.arctan2(X - cx, -(Y - cy)))
        d = np.maximum(d, (np.abs(ang) - 135) * rr * math.pi / 180)
        inside = -d
        p = height * prof("round", inside / (bw * 0.45))
        self.hf[sl] = np.where(inside > 0, np.maximum(self.hf[sl], level + p), self.hf[sl])
        self.paint(sl, np.clip(0.5 - d, 0, 1), col, SATIN)

    def shade(self, st):
        hf = self.hf
        gy, gx = np.gradient(hf)
        n = np.dstack([-gx, -gy, np.ones_like(gx)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        def nrm(v): v = np.array(v, np.float32); return v / np.linalg.norm(v)
        L1, L2, V = nrm(st.get("light_dir", [-0.35, -0.75, 0.95])), nrm([0.7, 0.15, 0.6]), np.array([0, 0, 1], np.float32)
        nl1 = np.clip(n @ L1, 0, 1)
        nl2 = np.clip(n @ L2, 0, 1)
        amb = 0.5 + 0.5 * n[..., 2]
        alb = self.alb * self.grain[..., None]
        flat = float(np.array([0, 0, 1], np.float32) @ L1)
        diff = alb * ((0.5 * amb + 0.58 * nl1 / flat * 0.9 + 0.1 * nl2) * st.get("exposure", 1.0))[..., None]
        Hh = nrm(L1 + V)
        nh = np.clip(n @ Hh, 1e-4, 1)
        spec = self.ks * np.exp(self.shin * np.log(nh))
        spec += np.where(self.shin < 100, self.ks * 0.3, 0) * np.exp(self.shin * 0.12 * np.log(nh))
        Ry = 2 * n[..., 2] * n[..., 1]
        env = 0.1 + 1.0 * np.clip(-Ry * 1.6 + 0.2, 0, 1) ** 1.5 + 0.2 * np.clip(Ry * 2 - 0.4, 0, 1)
        m = self.metal[..., None]
        col = diff * (1 - m) + alb * (0.25 + env[..., None]) * 0.8 * m
        col += spec[..., None] * (1 - m + m * alb)
        hb = blur(hf, 5 * S)
        ao = np.clip(1 - st.get("ao", 0.045) * np.maximum(hb - hf, 0), 0.5, 1)
        sh, li = st["shadow"], st.get("light")
        if st.get("shadow_mode") == "ray":
            # march towards the light: a pixel is shadowed only by surface that rises above the ray to it;
            # the penumbra widens with distance (a large, soft light)
            lxy = math.hypot(L1[0], L1[1])
            dx, dy, tan_e = L1[0] / lxy, L1[1] / lxy, L1[2] / lxy
            occ = np.zeros_like(hf)
            for i in range(1, sh.get("steps", 28) + 1):
                q = np.roll(np.roll(hf, -int(round(dy * i)), axis=0), -int(round(dx * i)), axis=1)
                rise_ = q - hf - i * tan_e
                occ = np.maximum(occ, np.clip(rise_ / (0.6 + 0.45 * i), 0, 1))
            shadow = blur(occ, max(1, S)) * sh["max"]
            # plus a soft drop shadow, mostly downward, so every object shades the surface around it
            src = np.roll(np.roll(hf, sh["off"][1] * S, axis=0), sh["off"][0] * S, axis=1)
            soft = np.clip((blur(src, sh["blur"] * S) - hf) * sh["k"], 0, sh.get("soft_max", 0.25))
            shadow = 1 - (1 - shadow) * (1 - soft)
        else:
            src = np.roll(np.roll(hf, sh["off"][1] * S, axis=0), sh["off"][0] * S, axis=1)
            hs = blur(src, sh["blur"] * S)
            shadow = np.clip((hs - hf) * sh["k"], 0, sh["max"])
        col *= (ao * (1 - shadow))[..., None]
        if li:  # light side of a soft form: the panel brightens towards the light
            srcl = np.roll(np.roll(hf, -sh["off"][1] * S, axis=0), -sh["off"][0] * S, axis=1)
            hl = blur(srcl, li["blur"] * S)
            light = np.clip((hl - hf) * li["k"], 0, li["max"])
            col = col + (lin(np.float32(1.0)) - col) * light[..., None] * 0.6
        col += self.emis
        return srgb(col)


def sd_rrect(X, Y, cx, cy, hw, hh, r):
    qx = np.abs(X - cx) - (hw - r)
    qy = np.abs(Y - cy) - (hh - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def blur(a, r):
    r = int(max(1, r))
    for _ in range(3):
        a = _box(_box(a, r, 0), r, 1)
    return a


def _box(a, r, axis):
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


# ---------------------------------------------------------------- layout (Max points)
SCREEN = (12, 44, 936, 240)
PLATES = [(12, 296, 300, 226), (322, 296, 316, 226), (648, 296, 300, 226), (12, 534, 936, 94)]
KNOBS = [  # cx, cy, r, value, label, enabled
    (68, 376, 19, 0.0, "POLY LO", 1), (162, 376, 19, 0.25, "POLY HI", 1), (256, 376, 19, 0.45, "TEMP", 1),
    (68, 460, 19, 0.2, "LEN MIN", 1), (162, 460, 19, 0.55, "LEN MAX", 1), (256, 460, 19, 0.6, "DENS", 0),
    (382, 378, 25, 0.5, "TEMP", 1), (480, 378, 25, 0.95, "TOP-P", 1), (578, 378, 25, 0.0, "TOP-K", 1),
    (382, 464, 18, 0.25, "ESC", 1), (480, 464, 18, 0.4, "TAKES", 1), (578, 464, 18, 0.6, "SEED", 1),
    (686, 360, 14, 0.18, "KEY", 1), (742, 360, 14, 0.42, "MODE", 1), (798, 360, 14, 0.8, "STR", 1),
    (854, 360, 14, 0.22, "LO", 1), (910, 360, 14, 0.62, "HI", 1),
]
STEPS = [1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0]
KEYS = [  # x, y, w, h, label, lit, text size
    (W - 184, 9, 80, 24, "ENGINE", 0, 8), (W - 96, 9, 80, 24, "SETUP", 0, 8),
    (192, 305, 50, 20, "FILL", 1, 8), (248, 305, 50, 20, "CONT", 0, 8),
    (664, 468, 62, 24, "SCALE", 1, 8), (732, 468, 62, 24, "VEL", 1, 8), (800, 468, 62, 24, "MICRO", 0, 8), (868, 468, 62, 24, "RMX", 0, 8),
    (30, 556, 50, 50, "", 0, 13), (88, 556, 50, 50, "1", 1, 13), (146, 556, 50, 50, "2", 0, 13), (204, 556, 50, 50, "3", 0, 13), (262, 556, 50, 50, "4", 0, 13),
    (540, 562, 90, 38, "KEEP", 0, 9.5),
]
GENERATE = (652, 554, 278, 54)
TITLES = [(28, 314, "TARGET"), (338, 314, "SAMPLE"), (664, 314, "SHAPE")]
SCENE = [("PNO", "C", "CCCCCCCC", "keys"), ("BASS", "T", "CCCCGGGG", "bass"), ("DRUM", "C", "CCCCCCCC", "drums"),
         ("PAD", "I", "CCCCCCCC", "pad"), ("LEAD", "T", "GGGGEEEE", "lead"), ("STR", "C", "CCCCEEEE", "pad")]


def steps_rects():
    return [(664 + i * 16.4 + (i // 4) * 2.5, 412, 14, 30, v) for i, v in enumerate(STEPS)]


def notes_for(ab, kind, bar):
    rs = np.random.RandomState((ord(ab[0]) * 131 + len(ab) * 17) * 977 + bar * 7919)
    r = rs.rand
    out = []
    if kind == "drums":
        for i in range(16):
            if i % 4 == 0: out.append((i / 16, 0.05, 0.85))
            if i % 8 == 4: out.append((i / 16, 0.05, 0.55))
            if r() > 0.35: out.append((i / 16, 0.035, 0.2))
        return out
    if kind == "pad":
        b = 0.25 + r() * 0.3
        return [(0, 0.96, b), (0, 0.96, b + 0.18), (0, 0.96, b + 0.34)]
    n = 5 + int(r() * 3) if kind == "bass" else 6 + int(r() * 5)
    x, p = 0.0, 0.3 + r() * 0.4
    for _ in range(n):
        if x >= 0.95: break
        ln = (0.1 if kind == "bass" else 0.06) + r() * 0.14
        p = min(0.88, max(0.12, p + (r() - 0.5) * 0.35))
        out.append((x, min(ln, 0.98 - x), p))
        if kind == "keys" and r() > 0.5: out.append((x, min(ln, 0.98 - x), min(0.9, p + 0.18)))
        x += ln + r() * 0.06
    return out


# ---------------------------------------------------------------- full panel
def key_part(c, st, x, y, w, h, lit, level):
    k, s = st["key"], S
    X, Y_, Wd, Hd = x * s, y * s, w * s, h * s
    shp = k["shape"]
    r = {"pill": min(w, h) / 2, "round": 6, "square": 2.5, "well": 6, "flush": 4, "dark": 6, "korry": 3, "study": 3}[shp] * s
    hh = k["h"] * s
    col = P["lit"] if (lit and k["lit"] in ("press",)) else P["key"]
    wpx = max(0.6 * s, k["w"] * min(Wd, Hd))
    top = None
    if k["top"] and k["top"][0] == "dish":
        amt = k["top"][1] * hh * 3
        cx, cy = X + Wd / 2, Y_ + Hd / 2
        top = lambda XX, YY, ins: -amt * np.clip(1 - ((XX - cx) / (Wd / 2)) ** 2 - ((YY - cy) / (Hd / 2)) ** 2 * 0.0, 0, 1) * np.clip(ins / (2 * s), 0, 1)
    if shp == "study":
        import button_studies as B
        dict((d_[0], d_[3]) for d_ in B.DESIGNS)[k["design"]](c, x, y, w, h, lit)
        return
    if shp == "korry":
        # cockpit push-button: raised bezel, glass face recessed inside it
        m = (2.6 if min(w, h) > 24 else 1.8) * s
        c.rrect(X, Y_, Wd, Hd, 3 * s, hh, 1.3 * s, "round", P["bezel"], (40, 0.3, 0), level)
        c.rrect(X + m, Y_ + m, Wd - 2 * m, Hd - 2 * m, 1.5 * s, 1.0 * s, 0.5 * s, "round", P["face_lit"] if lit else P["face"],
                (120, 0.45, 0), level + hh, sink=True, emis=("#FFFFFF", 0.06) if lit else None)
        return
    if shp == "dark":
        rr = min(8 * s, min(Wd, Hd) * 0.24)
        c.rrect(X - 2.5 * s, Y_ - 2.5 * s, Wd + 5 * s, Hd + 5 * s, rr + 2.5 * s, 0.9 * s, 1.6 * s, "soft", P["plate"], MATTE, level, sink=True)
        cxk, cyk, hw_, hh_ = X + Wd / 2, Y_ + Hd / 2, Wd / 2, Hd / 2
        edge = min(3.2 * s, 0.22 * min(Wd, Hd))
        # rounded edge, then a smooth pillow over the whole cap (separable, so no diagonal creases)
        pillow = lambda XX, YY, ins: 0.9 * s * (1 - np.clip(np.abs(XX - cxk) / hw_, 0, 1) ** 4) * (1 - np.clip(np.abs(YY - cyk) / hh_, 0, 1) ** 4)
        c.rrect(X, Y_, Wd, Hd, rr, hh, edge, "round", P["key"], (60, 0.35, 0), level - 0.9 * s, top=pillow)
        return
    if shp == "well":
        c.rrect(X - 3 * s, Y_ - 3 * s, Wd + 6 * s, Hd + 6 * s, r + 3 * s, 3.5 * s, 2.5 * s, "soft", P["plate"], MATTE, level, sink=True)
        lv = level - 3.5 * s
        c.rrect(X, Y_, Wd, Hd, r, hh * (0.55 if lit else 1.0), wpx, k["prof"], col, SATIN, lv)
    elif shp == "flush":
        c.groove(lambda XX, YY: sd_rrect(XX, YY, X + Wd / 2, Y_ + Hd / 2, Wd / 2, Hd / 2, r), (X - 6, Y_ - 6, X + Wd + 6, Y_ + Hd + 6), 0.55 * s, 0.9 * s, 0.18)
        c.rrect(X + 1.5 * s, Y_ + 1.5 * s, Wd - 3 * s, Hd - 3 * s, r, hh, wpx, k["prof"], P["key"], ALU if False else SATIN, level - 0.4 * s)
    else:
        press = 0.45 if (lit and k["lit"] == "press") else 1.0
        c.rrect(X, Y_, Wd, Hd, r, hh * press, wpx * (1 if shp != "pill" else 1), k["prof"], col, SATIN, level, top=top)


TOGGLE_KEYS = ("FILL", "CONT", "SCALE", "VEL", "MICRO", "RMX")

# Metacreation Lab mark (patchers/sections/metacreation-logo-black.svg, viewBox 105.63 x 137.32)
LOGO_POLYS = [[(26.41, 10.56), (84.51, 68.66), (26.41, 126.76), (36.97, 137.32), (105.63, 68.66), (36.97, 0), (26.41, 10.56)],
              [(31.69, 36.97), (0, 68.66), (31.69, 100.35), (42.25, 89.79), (21.13, 68.66), (42.25, 47.53), (31.69, 36.97)]]
HEADER_MID = 19.5                     # vertical centre of the header band (above the screen pocket)
LOGO_BOX = (18, HEADER_MID - 12, 24)   # x, y, height in points
TITLE = dict(x=52, cap=11, stroke=2.0, gap=4.6)


def wordmark(draw, ox, oy, k, cap, t, gap):
    """MIDI-GPT as extended geometric monoline lettering (square cuts, flat-sided bowls). k = px per pt.
    Returns the width in pt."""
    def L(x0, y0, x1, y1):
        draw.line([((ox + x0) * k, (oy + y0) * k), ((ox + x1) * k, (oy + y1) * k)], fill=255, width=max(1, int(round(t * k))))

    def A(cx, cy, r, a0, a1):
        R_ = r + t / 2
        draw.arc([(ox + cx - R_) * k, (oy + cy - R_) * k, (ox + cx + R_) * k, (oy + cy + R_) * k], a0, a1, fill=255, width=max(1, int(round(t * k))))

    h, hs = cap, t / 2
    x = 0.0
    # M: full verticals, a deep V
    w = 1.75 * h
    L(x + hs, 0, x + hs, h); L(x + w - hs, 0, x + w - hs, h)
    draw.line([((ox + x + hs) * k, (oy + hs) * k), ((ox + x + w / 2) * k, (oy + h * 0.66) * k), ((ox + x + w - hs) * k, (oy + hs) * k)],
              fill=255, width=max(1, int(round(t * k))), joint="curve")
    x += w + gap
    # I
    L(x + hs, 0, x + hs, h); x += t + gap
    # D: flat top and bottom, half-round right side
    w = 1.45 * h
    r = h / 2 - hs
    L(x + hs, 0, x + hs, h); L(x, hs, x + w - h / 2, hs); L(x, h - hs, x + w - h / 2, h - hs)
    A(x + w - h / 2, h / 2, r, 270, 90)
    x += w + gap
    # I
    L(x + hs, 0, x + hs, h); x += t + gap
    # hyphen
    w = 0.6 * h
    L(x, h / 2, x + w, h / 2); x += w + gap
    # G: half-round left side, flat top and bottom, spur and inner bar
    w = 1.5 * h
    L(x + h / 2, hs, x + w, hs); L(x + h / 2, h - hs, x + w, h - hs)
    A(x + h / 2, h / 2, r, 90, 270)
    L(x + w - hs, h * 0.52, x + w - hs, h); L(x + w * 0.56, h * 0.52, x + w, h * 0.52)
    x += w + gap
    # P: bowl over the top 60 %
    w = 1.3 * h
    bh = h * 0.6
    rb = bh / 2 - hs
    L(x + hs, 0, x + hs, h); L(x, hs, x + w - bh / 2, hs); L(x, bh - hs, x + w - bh / 2, bh - hs)
    A(x + w - bh / 2, bh / 2, rb, 270, 90)
    x += w + gap
    # T
    w = 1.35 * h
    L(x, hs, x + w, hs); L(x + w / 2, 0, x + w / 2, h)
    x += w
    return x


def engrave_mask(c, m, x0, y0, level=0.0, depth=2.0):
    """Sink a coverage mask (pixel grid, origin x0,y0 in px) into the panel as a brushed-metal inlay."""
    Hd, Wd = m.shape
    sl = (slice(y0, y0 + Hd), slice(x0, x0 + Wd))
    c.hf[sl] = np.minimum(c.hf[sl], level - depth * S * np.clip((m - 0.5) * 6 + 0.5, 0, 1))   # crisp, near-vertical walls
    c.paint(sl, m, "#AEB4BC", (70, 0.55, 0.85))
    rows = np.arange(Hd, dtype=np.float32)[:, None]
    c.alb[sl] *= (1 + 0.05 * np.sin(rows * 2.3) * m)[..., None]   # fine horizontal brushing


def engrave_logo(c, level=0.0):
    """The Metacreation mark and the MIDI-GPT wordmark, engraved and inlaid, centred on the header band."""
    up = 4
    x, y, hgt = LOGO_BOX
    sc = hgt / 137.32 * S
    Wd, Hd = int(math.ceil(105.63 * sc)) + 8, int(math.ceil(137.32 * sc)) + 8
    m = Image.new("L", (Wd * up, Hd * up), 0)
    dm = ImageDraw.Draw(m)
    for poly in LOGO_POLYS:
        dm.polygon([((px * sc + 4) * up, (py * sc + 4) * up) for (px, py) in poly], fill=255)
    m = np.asarray(m.resize((Wd, Hd), Image.LANCZOS), np.float32) / 255.0
    engrave_mask(c, m, int(round(x * S)) - 4, int(round(y * S)) - 4, level)
    # wordmark
    T = TITLE
    ty = HEADER_MID - T["cap"] / 2
    Wt, Ht = int(170 * S), int((T["cap"] + 4) * S)
    mt = Image.new("L", (Wt * up, Ht * up), 0)
    wordmark(ImageDraw.Draw(mt), 2, 2, S * up, T["cap"], T["stroke"], T["gap"])
    mt = np.asarray(mt.resize((Wt, Ht), Image.LANCZOS), np.float32) / 255.0
    engrave_mask(c, mt, int(round((T["x"] - 2) * S)), int(round((ty - 2) * S)), level)


def toggle_rects():
    """Pill toggles replacing the on/off keys: FILL/CONT becomes one switch, the shape options one each."""
    out = [(222, 309, 46, 16, 0)]
    for i, (lab, on) in enumerate((("SCALE", 1), ("VEL", 1), ("MICRO", 0), ("RMX", 0))):
        out.append((672 + i * 68, 488, 44, 16, on))
    return out


def toggle_part(c, x, y, w, h, on, level, kind=True):
    s = S
    if kind == "apple":
        # wide pill: a short sunken slot with a hard drop; a flat, crisp-edged pill thumb that
        # covers most of it, carrying an LED dot; the slot only peeks out at one end
        sh = h * 0.8
        c.rrect(x * s, (y + h / 2 - sh / 2) * s, w * s, sh * s, sh / 2 * s, 1.8 * s, 0.4 * s, "chamfer",
                P["track_on"] if on else P["track"], MATTE, level, sink=True)
        tw, th = w * 0.76, h * 1.3
        tx = x + w - tw + 2 if on else x - 2
        ty = y + h / 2 - th / 2
        c.rrect(tx * s, ty * s, tw * s, th * s, th / 2 * s, 3.2 * s, 0.3 * s, "round", P["knob"], SATIN, level)   # crisp vertical walls
        return
    c.rrect(x * s, y * s, w * s, h * s, h / 2 * s, 1.8 * s, 2.2 * s, "soft", P["plate"], MATTE, level, sink=True)
    tw, th = w * 0.58, h - 4
    tx = x + w - tw - 2 if on else x + 2
    c.rrect(tx * s, (y + 2) * s, tw * s, th * s, th / 2 * s, 4.2 * s, th * 0.45 * s, "round", P["knob"], SATIN, level - 1.8 * s,
            top=lambda XX, YY, ins: 0.4 * s * np.clip(ins / (th * 0.5 * s), 0, 1))


def render_panel(st):
    s = S
    c = Canvas(W * s, H * s, P["base"], MATTE)
    pm = st["panel"]
    # screen
    x, y, w, h = SCREEN
    if st.get("screen_pocket"):
        # a sunken pocket the shape of the screen plus a little padding, the glass sitting on its floor
        pad, dep = st["screen_pocket"]
        c.rrect((x - pad) * s, (y - pad) * s, (w + 2 * pad) * s, (h + 2 * pad) * s, (10 + pad) * s, dep * s, 0.5 * s, "chamfer",
                P["plate"], MATTE, 0, sink=True)
        c.rrect(x * s, y * s, w * s, h * s, 9 * s, 0.8 * s, 0.6 * s, "round", P["screen"], (30, 0.0, 0), -dep * s)
    else:
      c.rrect(x * s, y * s, w * s, h * s, (14 if pm == "soft" else 8) * s, st["screen_depth"] * s, st["screen_w"] * s,
            "soft" if pm in ("soft", "pockets") else "round", P["screen"], (30, 0.04 if "screen_spec" not in st else st["screen_spec"], 0), 0, sink=True)
    # module structure
    lvl = 0.0
    if pm == "soft":
        for (px, py, pw, ph) in PLATES:
            c.rrect(px * s, py * s, pw * s, ph * s, st["plate_r"] * s, st["plate_h"] * s, st["plate_w"] * s, "soft", P["plate"], MATTE, 0)
        lvl = st["plate_h"] * s
    elif pm == "pockets" and st.get("trench"):
        dep, a = st["trench"]
        for (px, py, pw, ph) in PLATES:
            c.rrect(px * s, py * s, pw * s, ph * s, st["plate_r"] * s, dep * s, a * s, "trench", P["plate"], MATTE, 0, sink=True)
        lvl = -0.1 * s
    elif pm == "pockets":
        for (px, py, pw, ph) in PLATES:
            c.rrect(px * s, py * s, pw * s, ph * s, st["plate_r"] * s, st["plate_h"] * s, st["plate_w"] * s, "soft", P["plate"], MATTE, 0, sink=True)
        lvl = -st["plate_h"] * s
    elif pm == "seams":
        for (px, py, pw, ph) in PLATES:
            c.groove(lambda XX, YY, px=px, py=py, pw=pw, ph=ph: sd_rrect(XX, YY, (px + pw / 2) * s, (py + ph / 2) * s, pw / 2 * s, ph / 2 * s, 3 * s),
                     ((px - 4) * s, (py - 4) * s, (px + pw + 4) * s, (py + ph + 4) * s), 0.6 * s, 1.4 * s, 0.22)
    elif pm == "flat":
        for (px, py, pw, ph) in PLATES[:3]:
            pass
    # recess around knobs (carved)
    if st.get("well"):
        rm, dm, wm = st["well"]
        for (cx, cy, r, v, lab, en) in KNOBS:
            c.disc(cx * s, cy * s, r * rm * s, r * dm * s, r * wm * s, "soft", P["plate"], MATTE, lvl, sink=True)
    # keys (and pill toggles for on/off settings)
    for (kx, ky, kw, kh, lab, lit, ts) in KEYS:
        if st.get("toggles") and lab in TOGGLE_KEYS:
            continue
        key_part(c, st, kx, ky, kw, kh, lit, 0 if ky < 40 else lvl)
    if st.get("toggles"):
        for (tx, ty, tw, th, on) in toggle_rects():
            toggle_part(c, tx, ty, tw, th, on, lvl, st.get("toggles"))
    for (sx, sy, sw, sh_, v) in steps_rects():
        key_part(c, st, sx, sy, sw, sh_, v, lvl)
    gx, gy, gw, gh = GENERATE
    key_part(c, dict(st, key=dict(st["key"], lit="press" if st["key"]["lit"] == "press" else st["key"]["lit"])), gx, gy, gw, gh, 0, lvl)
    # knobs
    if st.get("logo"):
        engrave_logo(c)
    for (cx, cy, r, v, lab, en) in KNOBS:
        base = lvl - (r * st["well"][1] * s if st.get("well") else 0)
        if st.get("collar") and st["collar"][2] > 0:
            cm, cw, cd = st["collar"]
            c.groove(lambda XX, YY, cx=cx, cy=cy: np.hypot(XX - cx * s, YY - cy * s) - r * cm * s,
                     ((cx - r * 1.5) * s, (cy - r * 1.5) * s, (cx + r * 1.5) * s, (cy + r * 1.5) * s), r * cw * 0.5 * s, cd * s * 2, 0.0)
        if st.get("band"):
            bm, bwm, bh = st["band"]
            c.arc_band(cx * s, cy * s, r * bm * s, r * bwm * s, r * bh * s, P["dark"], base)
        if st.get("label_pill"):
            ly = cy + r * st["well"][0] + 9
            lw = len(lab) * 5.2 + 16
            c.rrect((cx - lw / 2) * s, (ly - 6.5) * s, lw * s, 13 * s, 6.5 * s, 0.7 * s, 1.5 * s, "soft", P["plate"], MATTE, lvl, sink=True)
        c.knob(cx * s, cy * s, r * s, v, st, base)
    img = c.shade(st)
    return Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")


def font(size, bold=True):
    name = "AbletonSansSmall-Bold.ttf" if bold else "AbletonSansSmall-Regular.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, name), int(round(size * S * 2)))


def rgb(hx, a=255):
    return tuple(int(v * 255) for v in hexc(hx)) + (a,)


def overlay(st, base):
    """What jsui draws in code at runtime: notes, value indicators, lit states, printed legends. Drawn at 4x, downsampled."""
    Q = S * 2
    ov = Image.new("RGBA", (W * Q, H * Q), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ink, lab = rgb(P["ink"]), rgb(P["label"])

    def txt(x, y, s, size, col, anchor="mm", spacing=1.2):
        fnt = font(size)
        widths = [d.textlength(ch, font=fnt) for ch in s]
        tot = sum(widths) + spacing * Q * (len(s) - 1)
        cx = x * Q - (tot / 2 if anchor[0] == "m" else 0)
        for ch, wd in zip(s, widths):
            d.text((cx, y * Q), ch, font=fnt, fill=col, anchor="l" + anchor[1])
            cx += wd + spacing * Q

    if st.get("logo"):
        txt(LOGO_BOX[0] + 30, 21, "MIDI-GPT", 13, ink, anchor="lm", spacing=2.4)
    else:
        for (lx, ly, lw, lh) in ((20, 14, 4, 14), (27, 18, 4, 10), (34, 14, 4, 14)):
            d.rounded_rectangle([lx * Q, ly * Q, (lx + lw) * Q, (ly + lh) * Q], radius=2 * Q, fill=ink)
        txt(48, 21, "MIDI-GPT", 14, ink, anchor="lm", spacing=3)
    # piano roll, greyscale
    x, y, w, h = SCREEN
    gx, gw = x + 74, w - 74 - 14
    gap, rh, rg = 3, 33, 3
    bw = (gw - gap * 7) / 8
    if st.get("hud"):
        hud_roll(d, txt, Q, x, y, w, h, gx, gw, gap, rh, rg, bw)
    for i, (ab, role, cells, kind) in enumerate(SCENE if not st.get("hud") else []):
        yy = y + 18 + i * (rh + rg)
        ign, tgt = role == "I", role == "T"
        ar = 0.3 if ign else 1.0
        d.ellipse([(x + 15) * Q, (yy + rh / 2 - 3) * Q, (x + 21) * Q, (yy + rh / 2 + 3) * Q], fill=(240, 240, 238, 255) if tgt else (60, 60, 60, 255))
        txt(x + 28, yy + rh / 2, ab, 9.5, (240, 240, 238, 255) if tgt else (150, 150, 148, int(255 * ar)), anchor="lm", spacing=1)
        for b in range(8):
            k = cells[b]
            bx = gx + b * (bw + gap)
            box = [bx * Q, yy * Q, (bx + bw) * Q, (yy + rh) * Q]
            d.rounded_rectangle(box, radius=3 * Q, fill=(255, 255, 255, int((4 if k == "E" else 9) * ar)))
            if k == "E":
                continue
            gen = k == "G"
            if gen:
                d.rounded_rectangle(box, radius=3 * Q, fill=(255, 255, 255, 16))
                d.rectangle([(bx + 3) * Q, yy * Q, (bx + bw - 3) * Q, (yy + 1.5) * Q], fill=(245, 245, 243, 255))
            for (nx, nl, npitch) in notes_for(ab, kind, b):
                X0 = bx + 4 + nx * (bw - 8)
                X1 = X0 + max(2.5, nl * (bw - 8))
                Y0 = yy + rh - 5 - npitch * (rh - 11)
                d.rounded_rectangle([X0 * Q, (Y0 - 1.5) * Q, X1 * Q, (Y0 + 1.5) * Q], radius=1.2 * Q,
                                    fill=(245, 245, 243, int(255 * (1 if gen else 0.36) * ar)))
    for (tx, ty, s_) in TITLES:
        txt(tx, ty, s_, 8.5, lab, anchor="lm", spacing=1.8)
    # value indicators, by style
    ring = st["ring"]
    for (cx, cy, r, v, l, en) in KNOBS:
        if ring == "collar":
            rr = r * 1.22 - 2.5
            d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 405, fill=(0, 0, 0, 26), width=int(2.6 * Q))
            if en and v > 0.004:
                d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 135 + 270 * v, fill=ink, width=int(2.6 * Q))
            ly = cy + r * 1.22 + 11
        elif ring == "ticks":
            rr = r + 6
            for j in range(11):
                aa = math.radians(-135 + 27 * j)
                px, py = cx + rr * math.sin(aa), cy - rr * math.cos(aa)
                rad = 1.1 if j % 5 else 1.6
                d.ellipse([(px - rad) * Q, (py - rad) * Q, (px + rad) * Q, (py + rad) * Q], fill=ink)
            ly = cy + r + 15
        elif ring == "leds":
            rr = r * 1.16 + 6
            for j in range(15):
                aa = math.radians(-135 + 270 / 14 * j)
                px, py = cx + rr * math.sin(aa), cy - rr * math.cos(aa)
                on = en and j / 14 <= v + 1e-6
                d.ellipse([(px - 1.4) * Q, (py - 1.4) * Q, (px + 1.4) * Q, (py + 1.4) * Q], fill=ink if on else (0, 0, 0, 38))
            ly = cy + rr + 11
        elif ring == "floor":
            rr = r * 1.42 - 4
            d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 405, fill=(0, 0, 0, 22), width=int(2 * Q))
            if en and v > 0.004:
                d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 135 + 270 * v, fill=ink, width=int(2 * Q))
            ly = cy + r * 1.42 + 10
        elif ring == "fill":
            cm, cw, _ = st["collar"]
            rr, bw = r * cm, r * cw
            if en and v > 0.004:
                d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 135 + 270 * v, fill=ink, width=int(bw * Q))
            aa = math.radians(-135 + 270 * v)
            p0 = (cx + r * 0.42 * math.sin(aa), cy - r * 0.42 * math.cos(aa))
            p1 = (cx + r * 0.72 * math.sin(aa), cy - r * 0.72 * math.cos(aa))
            d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=ink + (60,) if len(ink) == 3 else ink[:3] + (60,), width=int(max(3.2, r * 0.17) * Q))
            d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=ink if en else lab, width=int(max(1.6, r * 0.085) * Q))
            ly = cy + rr + bw / 2 + 10
        elif ring == "band":
            bm, bwm, _ = st["band"]
            band, bw = r * bm, r * bwm
            n = max(10, int(round(r * 2.6)))
            if en:
                for j in range(n + 1):
                    ta = -135 + 270 * j / n
                    if ta > -135 + 270 * v + 0.01:
                        break
                    aa = math.radians(ta)
                    p0 = (cx + (band - bw * 0.36) * math.sin(aa), cy - (band - bw * 0.36) * math.cos(aa))
                    p1 = (cx + (band + bw * 0.36) * math.sin(aa), cy - (band + bw * 0.36) * math.cos(aa))
                    d.line([(p0[0] * Q, p0[1] * Q), (p1[0] * Q, p1[1] * Q)], fill=(241, 243, 246, 255), width=max(1, int(0.75 * Q)))
            for ta in (-135, 135, 0):
                aa = math.radians(ta)
                r0, r1 = (band + bw / 2, band + bw * 1.3) if ta == 0 else (band - bw / 2, band + bw * 1.2)
                d.line([((cx + r0 * math.sin(aa)) * Q, (cy - r0 * math.cos(aa)) * Q), ((cx + r1 * math.sin(aa)) * Q, (cy - r1 * math.cos(aa)) * Q)],
                       fill=rgb(P["dark"]), width=int(1.4 * Q))
            ly = cy + r * st["well"][0] + 9.3
        else:  # hairline
            rr = r + 6
            d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 405, fill=(0, 0, 0, 30), width=int(1 * Q))
            if en and v > 0.004:
                d.arc([(cx - rr) * Q, (cy - rr) * Q, (cx + rr) * Q, (cy + rr) * Q], 135, 135 + 270 * v, fill=ink, width=int(1.4 * Q))
            ly = cy + r + 15
        txt(cx, ly, l, 6.8 if st.get("label_pill") else 8, lab if en else lab[:3] + (100,), spacing=0.8 if st.get("label_pill") else 1.2)
    # key legends and lit states
    lit_mode = st["key"]["lit"]
    allkeys = [(kx, ky, kw, kh, l, lt, ts) for (kx, ky, kw, kh, l, lt, ts) in KEYS] + \
              [(sx, sy, sw, sh_, "", v, 8) for (sx, sy, sw, sh_, v) in steps_rects()]
    if st.get("toggles"):
        allkeys = [k_ for k_ in allkeys if k_[4] not in TOGGLE_KEYS]
        for (tx, ty, tw, th, on) in toggle_rects():
            tw2 = tw * 0.58
            mx = (tx + tw - tw2 / 2 - 2) if on else (tx + 2 + tw2 / 2)
            if st.get("toggles") != "apple":
                d.line([(mx * Q, (ty + th * 0.3) * Q), (mx * Q, (ty + th * 0.7) * Q)], fill=ink, width=int(1.3 * Q))
            else:   # LED dot on the thumb
                tw3 = tw * 0.76
                lx = (tx + tw - tw3 + 2 + tw3 / 2) if on else (tx - 2 + tw3 / 2)
                ly_ = ty + th / 2
                d.ellipse([(lx - 2) * Q, (ly_ - 2) * Q, (lx + 2) * Q, (ly_ + 2) * Q], fill=ink if on else (205, 210, 217, 255))
        for i, l in enumerate(("SCALE", "VEL", "MICRO", "RMX")):
            txt(672 + i * 68 + 22, 475, l, 6.8, rgb(P["label"]), spacing=0.9)
        for (bx, l) in ((196, "FILL"), (280, "CONT")):
            txt(bx, 317, l, 6.5, rgb(P["label"]), anchor="lm", spacing=0.5)
        for (bx, l, dirn) in ():
            d.line([(bx * Q, 305 * Q), (bx * Q, 301 * Q), ((bx + dirn * 18) * Q, 301 * Q)], fill=(195, 202, 211, 255), width=int(0.8 * Q))
            txt(bx + dirn * 21, 301, l, 6.5, rgb(P["label"]), anchor="lm" if dirn > 0 else "rm", spacing=0.5)
    if lit_mode == "study":
        import button_studies as B
        def stext(x_, y_, s_, size_, col_, anchor="mm"):
            d.text((x_ * Q, y_ * Q), s_, font=font(size_), fill=col_, anchor=anchor)
        for (kx, ky, kw, kh, l, lt, ts) in allkeys + [(GENERATE[0], GENERATE[1], GENERATE[2], GENERATE[3], "GENERATE", 0, 12)]:
            B.key_overlay(d, stext, Q, st["key"]["design"], kx, ky, kw, kh, l, lt, size=min(ts, 12))
            if (kx, ky) == (30, 556):   # original take: a return arrow instead of a letter
                mx, my = kx + kw / 2, ky + kh / 2 + (2 if st["key"]["design"] == "ledslit" else 0)
                ac = (150, 155, 164, 255) if st["key"]["design"] in ("ledslit", "glass") else (34, 38, 46, 255)
                lw_ = int(1.6 * Q)
                d.line([((mx + 6) * Q, (my - 6) * Q), ((mx + 6) * Q, (my + 2) * Q), ((mx - 6) * Q, (my + 2) * Q)], fill=ac, width=lw_, joint="curve")
                d.line([((mx - 6) * Q, (my + 2) * Q), ((mx - 2.5) * Q, (my - 1.5) * Q)], fill=ac, width=lw_)
                d.line([((mx - 6) * Q, (my + 2) * Q), ((mx - 2.5) * Q, (my + 5.5) * Q)], fill=ac, width=lw_)
        allkeys = []
    korry = lit_mode == "korry"
    for (kx, ky, kw, kh, l, lt, ts) in allkeys + ([(GENERATE[0], GENERATE[1], GENERATE[2], GENERATE[3], "GENERATE", 0, 12)] if korry else []):
        if korry:
            m = 2.6 if min(kw, kh) > 24 else 1.8
            fx0, fy0, fx1, fy1 = kx + m, ky + m, kx + kw - m, ky + kh - m
            on = (245, 247, 250, 255)
            off = (110, 115, 124, 255)
            if kh >= 34:   # two-part legend: name on top, an indicator bar below that lights
                txt(kx + kw / 2, ky + kh * 0.38, l, ts if ts < 12 else 11, on if lt else off, spacing=1.2 if len(l) > 1 else 0)
                bar = [(kx + kw / 2 - min(14, kw * 0.28)) * Q, (ky + kh * 0.72) * Q, (kx + kw / 2 + min(14, kw * 0.28)) * Q, (ky + kh * 0.72 + 2.4) * Q]
                if lt:
                    d.rounded_rectangle([bar[0] - 2 * Q, bar[1] - 2 * Q, bar[2] + 2 * Q, bar[3] + 2 * Q], radius=2 * Q, fill=(255, 255, 255, 50))
                d.rounded_rectangle(bar, radius=Q, fill=on if lt else (60, 63, 70, 255))
            elif l:
                txt(kx + kw / 2, ky + kh / 2 + 0.5, l, min(ts, 7.5), on if lt else off, spacing=1.1)
            else:          # rhythm steps: the whole face glows
                if lt:
                    d.rounded_rectangle([fx0 * Q, fy0 * Q, fx1 * Q, fy1 * Q], radius=1.5 * Q, fill=(235, 238, 242, 230))
            continue
        if lit_mode == "corner":
            lx, lyy = kx + kw - min(7, kw * 0.25), ky + min(7, kh * 0.22)
            if lt:
                d.ellipse([(lx - 3.2) * Q, (lyy - 3.2) * Q, (lx + 3.2) * Q, (lyy + 3.2) * Q], fill=(255, 255, 255, 70))
                d.ellipse([(lx - 1.7) * Q, (lyy - 1.7) * Q, (lx + 1.7) * Q, (lyy + 1.7) * Q], fill=(255, 255, 255, 255))
            else:
                d.ellipse([(lx - 1.9) * Q, (lyy - 1.9) * Q, (lx + 1.9) * Q, (lyy + 1.9) * Q], fill=(14, 17, 22, 255), outline=(74, 81, 96, 255), width=max(1, int(0.6 * Q)))
        tc = rgb(P[st["key"]["text"]]) if st["key"].get("text") else (rgb(P["on_lit"]) if (lt and lit_mode == "press") else rgb(P["ink"]))
        if lt and lit_mode == "dot":
            cxk, cyk = kx + kw / 2, ky + (5 if kh > 26 else 4) if l else ky + kh / 2
            if not l:
                d.ellipse([(cxk - 2) * Q, (cyk - 2) * Q, (cxk + 2) * Q, (cyk + 2) * Q], fill=ink)
            else:
                d.ellipse([(kx + 7 - 2) * Q, (ky + kh / 2 - 2) * Q, (kx + 7 + 2) * Q, (ky + kh / 2 + 2) * Q], fill=ink)
        if lt and lit_mode == "led":
            d.rounded_rectangle([(kx + kw / 2 - 6) * Q, (ky + 3) * Q, (kx + kw / 2 + 6) * Q, (ky + 5) * Q], radius=Q, fill=ink)
        if lt and lit_mode == "glow":
            d.rounded_rectangle([(kx + 3) * Q, (ky + kh - 4) * Q, (kx + kw - 3) * Q, (ky + kh - 3) * Q], radius=Q, fill=ink)
        if l:
            yoff = 2 if (lit_mode == "led" and kh < 30) else 0.5
            txt(kx + kw / 2 + (3 if (lt and lit_mode == "dot") else 0), ky + kh / 2 + yoff, l, ts, tc, spacing=0.6 if ts > 10 else 1.2)
    if st.get("toggles"):
        # printed scale under the rhythm steps: a tick per step, longer on each beat, beat numbers
        for (sx, sy, sw_, sh_, v) in steps_rects():
            mx = sx + sw_ / 2
            beat = steps_rects().index((sx, sy, sw_, sh_, v)) % 4 == 0
            d.line([(mx * Q, (sy + sh_ + 3) * Q), (mx * Q, (sy + sh_ + (7 if beat else 5)) * Q)], fill=lab, width=max(1, int((1.1 if beat else 0.8) * Q)))
            if beat:
                txt(mx, sy + sh_ + 13, str(steps_rects().index((sx, sy, sw_, sh_, v)) // 4 + 1), 7, lab, spacing=0)
        txt(912, 455, "1/16", 7, lab, anchor="lm", spacing=0.6)
    else:
        txt(664, 452, "1/16", 7.5, lab, anchor="lm", spacing=1)
    for i in range(4):
        cx = 330 + i * 12
        d.ellipse([(cx - 3) * Q, (581 - 3) * Q, (cx + 3) * Q, (581 + 3) * Q], fill=ink if i == 0 else (0, 0, 0, 40))
    gx, gy, gw, gh = GENERATE
    gc = rgb(P[st["key"]["text"]]) if st["key"].get("text") else ink
    if korry or lit_mode == "study":
        gx = -1000
    d.polygon([((gx + 92) * Q, (gy + 19) * Q), ((gx + 106) * Q, (gy + 27) * Q), ((gx + 92) * Q, (gy + 35) * Q)], fill=gc)
    txt(gx + 118, gy + 27.5, "GENERATE", 13, gc, anchor="lm", spacing=2.6)
    ov = ov.resize((W * S, H * S), Image.LANCZOS)
    out = base.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


HUD = dict(green=(60, 224, 122), cyan=(56, 214, 240), magenta=(255, 79, 216), white=(226, 232, 238), amber=(255, 186, 60))


def hud_roll(d, txt, Q, x, y, w, h, gx, gw, gap, rh, rg, bw):
    """Piano roll as an avionics display: thin line work, HUD colours, no fills."""
    G, C, M, Wt = HUD["green"], HUD["cyan"], HUD["magenta"], HUD["white"]
    lw = max(1, int(0.8 * Q))
    # bar ruler: numbers and tick marks in green
    for b in range(8):
        bx = gx + b * (bw + gap)
        txt(bx + 3, y + 10, "%02d" % (b + 1), 7, G + (230,), anchor="lm", spacing=0.6)
        d.line([(bx * Q, (y + 15) * Q), (bx * Q, (y + 18) * Q)], fill=G + (200,), width=lw)
    d.line([(gx * Q, (y + 15) * Q), ((gx + gw) * Q, (y + 15) * Q)], fill=G + (90,), width=lw)
    for i, (ab, role, cells, kind) in enumerate(SCENE):
        rh = 29
        yy = y + 22 + i * (rh + 3)
        ign, tgt = role == "I", role == "T"
        a = 0.3 if ign else 1.0
        lab_col = (C if tgt else Wt) + (int(255 * (1 if tgt else 0.7) * a),)
        if tgt:
            d.polygon([((x + 14) * Q, (yy + rh / 2 - 3.5) * Q), ((x + 20) * Q, (yy + rh / 2) * Q), ((x + 14) * Q, (yy + rh / 2 + 3.5) * Q)], fill=C + (255,))
        txt(x + 26, yy + rh / 2, ab, 8.5, lab_col, anchor="lm", spacing=1.2)
        for b in range(8):
            k = cells[b]
            bx = gx + b * (bw + gap)
            x0, y0, x1, y1 = bx * Q, yy * Q, (bx + bw) * Q, (yy + rh) * Q
            if k == "E":
                for xx in range(int(x0), int(x1), int(6 * Q)):    # dashed outline for empty bars
                    d.line([(xx, y0), (min(xx + 3 * Q, x1), y0)], fill=G + (int(60 * a),), width=lw)
                    d.line([(xx, y1), (min(xx + 3 * Q, x1), y1)], fill=G + (int(60 * a),), width=lw)
                continue
            gen = k == "G"
            col = M if gen else G
            if gen:   # corner brackets around generated bars
                L_ = 6 * Q
                for (cx_, cy_, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                    d.line([(cx_, cy_), (cx_ + dx * L_, cy_)], fill=M + (255,), width=int(1.2 * Q))
                    d.line([(cx_, cy_), (cx_, cy_ + dy * L_)], fill=M + (255,), width=int(1.2 * Q))
            else:
                d.rectangle([x0, y0, x1, y1], outline=G + (int(70 * a),), width=lw)
            for q in (1, 2, 3):   # beat ticks
                tx = x0 + (x1 - x0) * q / 4
                d.line([(tx, y1 - 2 * Q), (tx, y1)], fill=col + (int(110 * a),), width=lw)
            for (nx, nl, npitch) in notes_for(ab, kind, b):
                X0 = bx + 4 + nx * (bw - 8)
                X1 = X0 + max(2.5, nl * (bw - 8))
                Y0 = yy + rh - 6 - npitch * (rh - 12)
                d.rectangle([X0 * Q, (Y0 - 1) * Q, X1 * Q, (Y0 + 1) * Q], fill=col + (int(255 * (1 if gen else 0.6) * a),))
    # status line along the bottom edge
    txt(x + 14, y + h - 10, "TGT BASS LEAD", 7, C + (220,), anchor="lm", spacing=1)
    txt(x + 140, y + h - 10, "TAKE 1/4", 7, M + (230,), anchor="lm", spacing=1)
    txt(x + w - 82, y + h - 10, "LINK 410MS", 7, G + (220,), anchor="lm", spacing=1)


def knob_strip(st, r=25, frames=64):
    """One knob, every angle, side by side (pictctrl / jsui frame layout)."""
    pad = 18
    fw = (2 * (r + pad)) * S
    strip = Image.new("RGB", (fw * frames, fw))
    for i in range(frames):
        c = Canvas(fw, fw, P["plate"] if st["panel"] in ("soft", "pockets") else P["base"], MATTE, grain=0.0, seed=2)
        if st.get("well"):
            rm, dm, wm = st["well"]
            c.disc(fw / 2, fw / 2, r * rm * S, r * dm * S, r * wm * S, "soft", P["plate"], MATTE, 0, sink=True)
        c.knob(fw / 2, fw / 2, r * S, i / (frames - 1), st, -(r * st["well"][1] * S) if st.get("well") else 0)
        img = Image.fromarray((c.shade(st) * 255 + 0.5).astype(np.uint8), "RGB")
        strip.paste(img, (i * fw, 0))
    return strip, fw


def compose(raw, style, out_dir):
    """Blender's panel render + the runtime layer -> panel_<style>.jpg (2x) and thumb_<style>.jpg (1x)."""
    use_palette(STYLES[style])
    img = overlay(STYLES[style], Image.open(raw).convert("RGB"))
    img.save(os.path.join(out_dir, "panel_%s.jpg" % style), quality=92, subsampling=0)
    img.resize((W, H), Image.LANCZOS).save(os.path.join(out_dir, "thumb_%s.jpg" % style), quality=88)


def stitch(frames_dir, out):
    """Stitch Blender's knob frames side by side (pictctrl / jsui layout)."""
    files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    ims = [Image.open(os.path.join(frames_dir, f)).convert("RGB") for f in files]
    fw, fh = ims[0].size
    st = Image.new("RGB", (fw * len(ims), fh))
    for i, im in enumerate(ims):
        st.paste(im, (i * fw, 0))
    st.save(out, optimize=True)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "compose":
        return compose(sys.argv[2], sys.argv[3], sys.argv[4])
    if len(sys.argv) >= 2 and sys.argv[1] == "strip":
        return stitch(sys.argv[2], sys.argv[3])
    if len(sys.argv) < 2 or sys.argv[1] not in ("mock", "list"):
        sys.exit(__doc__)
    if sys.argv[1] == "list":
        print("\n".join(STYLES))
        return
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for n in sys.argv[3:] or list(STYLES):
        st = STYLES[n]
        use_palette(st)
        img = overlay(st, render_panel(st))
        img.save(os.path.join(out, "panel_%s.jpg" % n), quality=90, subsampling=0)
        img.resize((W, H), Image.LANCZOS).save(os.path.join(out, "thumb_%s.jpg" % n), quality=86)
        strip, fw = knob_strip(st)
        strip.save(os.path.join(out, "knob_%s.png" % n), optimize=True)
        print(n, "frame", fw)


if __name__ == "__main__":
    main()
