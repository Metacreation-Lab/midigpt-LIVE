#!/usr/bin/env python3
"""
Quick 3D view of the MIDI-GPT panel for the release video (storyboard / animatic stage).

The panel is a height field textured with a real capture of the device: the colour is the
screenshot (so every frame shows true states: notes, takes, labels), the relief comes from the
panel's layout (javascript/midigpt_panel_spec.js): bays and the screen are recessed, knobs,
keys and toggles stand up as separate parts. Parts can rise ("lift"), press down, and cast a
shadow on the plate. Rendered by splatting every texel through a pinhole camera into a
z-buffer (numpy only), with a few hole-filling passes.

  from panel3d import Panel, Camera, render
  p = Panel("panel_tex.png")
  img = render(p, Camera(pos=(480, 900, 520), look=(480, 300, 0), fov=40), lift={"GENERATE": -3})
"""

import json
import math
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC_JS = os.path.join(ROOT, "javascript", "midigpt_panel_spec.js")
W_PT, H_PT = 960, 640


def load_spec():
    s = open(SPEC_JS).read()
    return json.loads(s[s.index("SPEC: ") + 6:s.index(",\n  THEME")])


def parts_main(spec, page="main"):
    """Every part of a page: (name, kind, geometry in pt). kind: knob (cx, cy, r) or box (x, y, w, h)."""
    out = []
    m = spec["pages"][page]
    if page == "main":
        # TRACK: the device shows only the knobs the selected track uses, centred in the bay (midigpt_panel.js trackLayout)
        out += [("POLY", "knob", (105, 387, 26)), ("LENGTH", "knob", (291, 387, 26))]
    for name, cx, cy, r in m["knobs"]:
        if (page != "main" or cx > 384) and name != "SEED":      # main: only the SAMPLE bay's knobs; SEED is a readout now
            out.append((name, "knob", (cx, cy, r)))          # the knob body only: its LED ring stays on the panel
    for name, x, y, w, h in m["toggles"]:
        out.append((name, "box", (x, y, w, h)))
    for name, x, y, w, h in m.get("keys", []):
        out.append((name, "box", (x, y, w, h)))
    for name, x, y, w, h in spec["top_keys"]:
        out.append((name, "box", (x, y, w, h)))
    o = spec["output"]
    for i, (x, y, w, h) in enumerate(o["takes"]):
        out.append(("TAKE%d" % i, "box", (x, y, w, h)))
    out.append(("KEEP", "box", tuple(o["keep"])))
    out.append(("GENERATE", "box", tuple(o["generate"])))
    e = spec["extras"]
    for name, cx, cy, r in e["knobs"]:
        out.append((name, "knob", (cx, cy, r)))
    for name, x, y, w, h in e["toggles"]:
        out.append((name, "box", (x, y, w, h)))
    return out


class Panel:
    """Texture, base height (px) and a part-id map, at the texture's resolution (2 px per pt)."""

    def __init__(self, tex_path, spec=None, page="main"):
        spec = spec or load_spec()
        tex = np.asarray(Image.open(tex_path).convert("RGB"), np.float32) / 255.0
        self.tex = tex
        H, W = tex.shape[:2]
        self.k = W / W_PT
        k = self.k
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy
        z = np.zeros((H, W), np.float32)
        # recesses: the bays, the screen, the masks bay
        def rect(x, y, w, h):
            return (xx >= x * k) & (xx < (x + w) * k) & (yy >= y * k) & (yy < (y + h) * k)
        for (x, y, w, h, _) in spec["pages"][page]["bays"] + [spec["output"]["bay"], spec["extras"]["bay"]]:
            z[rect(x, y, w, h)] = -3 * k
        sx, sy, sw, sh = spec["screen"]
        z[rect(sx, sy, sw, sh)] = -5 * k
        if page == "main":                       # the seed readout: a small screen in its own dip
            z[rect(598, 395, 76, 20)] = -2 * k
        self.base = z
        self.parts = parts_main(spec, page)
        self.pid = np.full((H, W), -1, np.int32)
        self.part_h = np.zeros((H, W), np.float32)
        for i, (name, kind, g) in enumerate(self.parts):
            if kind == "knob":
                cx, cy, r = g
                d = np.hypot(xx - cx * k, yy - cy * k)
                m = d <= r * k
                h = np.where(m, (14 - 6 * (d / (r * k)) ** 6) * k, 0)       # a cylinder with a rounded edge
            else:
                x, y, w, h_ = g
                m = rect(x, y, w, h_)
                h = np.where(m, 6 * k, 0)
            self.pid[m] = i
            self.part_h = np.maximum(self.part_h, h)
        self.names = {name: i for i, (name, _, _) in enumerate(self.parts)}


class Camera:
    def __init__(self, pos, look, fov=45.0, up=(0, 0, 1)):
        self.pos = np.array(pos, np.float32)
        self.look = np.array(look, np.float32)
        self.fov = fov
        self.up = np.array(up, np.float32)

    def basis(self):
        f = self.look - self.pos
        f /= np.linalg.norm(f)
        r = np.cross(f, self.up)
        if np.linalg.norm(r) < 1e-6:
            r = np.array([1, 0, 0], np.float32)
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        return r, u, f


def lerp_cam(a, b, t):
    s = t * t * (3 - 2 * t)            # smoothstep
    return Camera(a.pos + (b.pos - a.pos) * s, a.look + (b.look - a.look) * s, a.fov + (b.fov - a.fov) * s)


def render(p, cam, size=(1280, 720), lift=None, exaggerate=1.0, glow=None, bg=(0.035, 0.035, 0.038), step=1, rot=None,
           fade=1.0):
    """lift: {part name: pt} raises (or, negative, presses) a part. glow: {part name: (r, g, b)} adds light.
    rot: {knob name: degrees} turns a knob. fade: overall brightness (0 = black)."""
    lift = lift or {}
    k = p.k
    Wo, Ho = size
    # world points: x right, y towards the viewer (screen rows), z up; the panel lies in z = 0, y grows downwards on it
    xs = p.xx[::step, ::step].ravel()
    ys = p.yy[::step, ::step].ravel()
    pid = p.pid[::step, ::step].ravel()
    col = p.tex[::step, ::step].reshape(-1, 3).copy()
    z = (p.base + p.part_h)[::step, ::step].ravel() * exaggerate
    off = np.zeros_like(z)
    for name, v in lift.items():
        off[pid == p.names[name]] = v * k
    z = z + off
    for name, deg in (rot or {}).items():          # turn a knob: rotate its texels about its centre
        _, kind, g = p.parts[p.names[name]]
        m = pid == p.names[name]
        cx_, cy_ = g[0] * k, g[1] * k
        a = math.radians(deg)
        dx, dy = xs[m] - cx_, ys[m] - cy_
        xs = xs.copy(); ys = ys.copy()
        xs[m] = cx_ + dx * math.cos(a) - dy * math.sin(a)
        ys[m] = cy_ + dx * math.sin(a) + dy * math.cos(a)
    # shadows of raised parts on the plate below them (light from the upper left)
    lifted = np.zeros(p.pid.shape, np.float32)
    for name, v in lift.items():
        if v > 0:
            lifted[p.pid == p.names[name]] = min(1.0, v / 40.0)
    if lifted.any():
        sh = Image.fromarray((lifted * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))
        sh = np.roll(np.roll(np.asarray(sh, np.float32) / 255.0, 22, axis=0), 18, axis=1)[::step, ::step].ravel()
        col *= (1 - 0.65 * sh * (off <= 0))[:, None]
    # walls: lifted parts get their sides, a few darkened copies between the plate and the part
    extra = []
    for name, v in lift.items():
        if v > 2:
            m = pid == p.names[name]
            for f in np.linspace(0.04, 0.97, max(6, int(v * k / 1.2))):
                extra.append((xs[m], ys[m], (z[m] - off[m]) + off[m] * f, col[m] * (0.35 + 0.3 * f)))
    if extra:
        xs = np.concatenate([xs] + [e[0] for e in extra])
        ys = np.concatenate([ys] + [e[1] for e in extra])
        zw = np.concatenate([z] + [e[2] for e in extra])
        col = np.concatenate([col] + [e[3] for e in extra])
    else:
        zw = z
    if glow:
        for name, rgb in glow.items():
            m = np.zeros(len(xs), bool)
            m[:len(pid)] = pid == p.names[name]
            col[m] = np.clip(col[m] + np.array(rgb, np.float32) * 0.35, 0, 1)
    # world: X = x, Y = -y (so the panel's top is "far"), Z = z
    P = np.stack([xs, -ys, zw], 1)
    r, u, f = cam.basis()
    d = P - cam.pos
    cz = d @ f
    cx = d @ r
    cy = d @ u
    ok = cz > 1
    fpx = 0.5 * Wo / math.tan(math.radians(cam.fov) / 2)
    sx = (Wo / 2 + fpx * cx[ok] / cz[ok]).astype(np.int32)
    sy = (Ho / 2 - fpx * cy[ok] / cz[ok]).astype(np.int32)
    depth = cz[ok]
    c = col[ok]
    inside = (sx >= 0) & (sx < Wo) & (sy >= 0) & (sy < Ho)
    sx, sy, depth, c = sx[inside], sy[inside], depth[inside], c[inside]
    order = np.argsort(-depth)                    # far first: nearer texels overwrite
    idx = sy[order] * Wo + sx[order]
    out = np.zeros((Ho * Wo, 3), np.float32)
    hit = np.zeros(Ho * Wo, bool)
    out[idx] = c[order]
    hit[idx] = True
    out = out.reshape(Ho, Wo, 3)
    hit = hit.reshape(Ho, Wo)
    # fill the holes splatting leaves when the camera is close: a few passes of neighbour averaging
    for _ in range(4):
        if hit.all():
            break
        acc = np.zeros_like(out)
        n = np.zeros(hit.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            acc += np.roll(np.roll(out * hit[..., None], dy, 0), dx, 1)
            n += np.roll(np.roll(hit.astype(np.float32), dy, 0), dx, 1)
        fill = (~hit) & (n > 0)
        out[fill] = acc[fill] / n[fill][:, None]
        hit = hit | fill
    out[~hit] = bg
    out *= fade
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
