#!/usr/bin/env python3
"""
Release trailer v3: the 3D panel, textured with screen recordings of the device performing each step, cut to a
recorded performance of the Minimal Techno trailer set.

  python3 tools/video/trailer3.py full|short <work dir> <audio.wav> <out dir> [--size 1280x720] [--fps 24] [--jobs 4] [--stills] [--draft]
      [--plates <dir>]   final cut: text, cards, logo and fades over the Blender plates (blender_trailer.py)

<work dir> holds tex/*.png (stills of the device) and ui/fr_<shot>/*.jpg (30 fps frames of each scripted screen
recording). The audio is Live's master from song bar 1 (a silent bar); the video starts at bar 2, and every
shot is placed in bars so cuts land on the music.
"""

import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from panel3d import Camera, Panel, lerp_cam, render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
TITLE = os.path.join(ROOT, "docs", "images", "title.png")
FONTS = "/Applications/Ableton Live 11 Suite.app/Contents/App-Resources/Fonts/"
BAR = 60.0 / 126 * 4
START_BAR = 2
PREROLL = {"full": 2, "short": 1}       # silent bars at the start of each recording (the video starts after them)
ORANGE = (255, 150, 70)


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def bump(t, t0, t1, hold=0.35):
    if t <= t0 or t >= t1:
        return 0.0
    u = (t - t0) / (t1 - t0)
    up, down = (1 - hold) / 2, (1 + hold) / 2
    if u < up:
        return smooth(u / up)
    if u > down:
        return smooth((1 - u) / (1 - down))
    return 1.0


C = Camera
# every view a notch further back than v2 (texture px; world y = -y)
TOPDOWN = C((960, -645, 3400), (960, -640, 0), 40)                       # the whole plugin, straight above
INTRO = (C((960, -3600, 2300), (960, -640, 0), 40), TOPDOWN)
WHOLE_HUD = (C((960, -2050, 2550), (960, -600, 0), 40), C((1000, -1980, 2450), (1000, -600, 0), 40))
GEN_WIDE = (C((1450, -1900, 1350), (1600, -880, 0), 40), C((1520, -1780, 1250), (1640, -890, 0), 40))
def sweep(y_look=-360, z=1250, back=-1150):
    return (C((300, back, z), (520, y_look, 0), 40), C((1500, back, z), (1450, y_look, 0), 40))
TAKES_SWEEP = sweep()
TRACK_VIEW = C((380, -1550, 1250), (380, -780, 0), 40)
SAMPLE_VIEW = C((1080, -1550, 1250), (1080, -780, 0), 40)
BUILD_KEYS = [(0.0, WHOLE_HUD[0]), (0.2, WHOLE_HUD[1]), (0.32, TRACK_VIEW), (0.5, C((430, -1530, 1230), (430, -780, 0), 40)),
              (0.62, SAMPLE_VIEW), (1.0, C((1130, -1520, 1200), (1130, -780, 0), 40))]
PEAK_ROLL = (C((1180, -1450, 1700), (1250, -330, 0), 40), C((1230, -1420, 1650), (1260, -330, 0), 40))
MASK_SCALE = (C((380, -1850, 1150), (420, -1170, 0), 40), C((440, -1820, 1100), (460, -1170, 0), 40))
KEEP_VIEW = (C((1200, -1500, 1500), (1300, -560, 0), 40), C((1450, -1550, 1300), (1550, -760, 0), 40))
MASKS_SWEEP = (C((350, -2000, 1150), (450, -1170, 0), 40), C((1550, -2000, 1150), (1550, -1170, 0), 40))
STATS_VIEW = (C((1640, -1650, 1150), (1640, -800, 0), 40), C((1660, -1600, 1080), (1650, -800, 0), 40))
PEAK_WIDE = (C((960, -2050, 2400), (960, -560, 0), 40), C((1000, -1980, 2300), (1000, -560, 0), 40))
ROLL_WIDE = (C((900, -1350, 1600), (960, -330, 0), 40), C((1020, -1320, 1550), (1020, -330, 0), 40))
ENGINE_WIDE = (C((640, -1800, 1700), (680, -720, 0), 40), C((700, -1760, 1650), (700, -720, 0), 40))
SETUP_WIDE = (C((700, -1800, 1700), (700, -720, 0), 40), C((660, -1760, 1650), (660, -720, 0), 40))
OUTRO = (C((960, -1400, 1700), (960, -640, 0), 40), C((960, -2900, 7200), (960, -720, 0), 38))


def rise(t, p):
    """The parts lift gently out of the plate, left to right, and settle."""
    return {"lift": {n: 10 * bump(t, 0.1 + 0.4 * p.parts[i][2][0] / 960.0, 0.95, 0.4) for n, i in p.names.items()}}


def glow(name, t0=0.0, t1=1.0, lift=8):
    def f(t, p):
        if name not in p.names:
            return {}
        a = bump(t, t0, t1, 0.6)
        knob = p.parts[p.names[name]][1] == "knob"            # lifted knobs grow textured walls: brighten only
        return {"lift": {name: 0 if knob else 4 * a}, "glow": {name: (0.1 * a, 0.07 * a, 0.03 * a)}}
    return f


def glows(*items):
    """items: (name, t0, t1) — several highlights over one shot."""
    def f(t, p):
        st = {"lift": {}, "glow": {}}
        for name, t0, t1 in items:
            if name in p.names:
                a = bump(t, t0, t1, 0.6)
                knob = p.parts[p.names[name]][1] == "knob"
                st["lift"][name] = 0 if knob else max(st["lift"].get(name, 0), 4 * a)
                st["glow"][name] = (0.1 * a, 0.07 * a, 0.03 * a)
        return st
    return f


def press(t, p):
    down = bump(t, 0.6, 0.98, 0.5)
    return {"lift": {"GENERATE": -4 * down}, "glow": {"GENERATE": tuple(c * smooth((t - 0.6) / 0.2) for c in (0.9, 0.5, 0.2))}}


def pulse(t, p):
    a = 0.5 + 0.5 * math.sin(t * math.pi * 4)
    return {"lift": {"GENERATE": -2}, "glow": {"GENERATE": (0.4 * a, 0.22 * a, 0.08 * a)}}


def none(t, p):
    return {}


T = BAR
# shot: (bar from, bar to, page, source, cameras, state, captions)
#   source: ("still", name) | ("video", recording, script time at the shot's start[, speed]) | ("freeze", recording, script time)
#   captions: [(t0, t1, title, subtitle)] in shot fractions
SHOTS = {
    "full": [
        (2, 6, "main", ("seq", "intro", 0.0), INTRO, rise, []),
        (6, 10, "main", ("seq", "build3", 0.0), BUILD_KEYS, glows(("POLY", 0.3, 0.52), ("TAKES", 0.58, 0.8)),
         [(0.0, 0.28, "Pick what to write", "AR: one click and the whole track gets written"),
          (0.28, 0.54, "Track controls", "Per track: make the lead monophonic, polyphony 1 to 1"),
          (0.54, 1.0, "Ask for takes", "A batch: several options from one click")]),
        (10, 12, "main", ("seq", "press3", 0.0), GEN_WIDE, lambda t, p: press(min(1, t * 2), p) if t < 0.5 else pulse(t, p),
         [(0.5, 1.0, "Generating", "MIDI-GPT listens to every track and writes a new one")]),
        (12, 16, "main", ("seq", "takes3", 0.0), TAKES_SWEEP, glow("TAKE1", 0.0, 0.4), [(0.05, 1.0, "Takes", "Several lead lines from one batch. This is take 1")]),
        (16, 20, "main", ("seq", "takes3", 4 * T), TAKES_SWEEP, glow("TAKE2", 0.0, 0.4), [(0.05, 1.0, "Pick the one you like", "Take 2")]),
        (20, 24, "main", ("seq", "takes3", 8 * T), KEEP_VIEW, glows(("TAKE3", 0.0, 0.35), ("KEEP", 0.7, 0.98)),
         [(0.05, 0.62, "Switch any time", "Take 3"), (0.62, 1.0, "Keep", "Writes the take into your clip")]),
        (24, 28, "main", ("seq", "masks3", 0.0), MASKS_SWEEP, glows(("RHYTHM", 0.05, 0.3), ("REMIX", 0.55, 0.8)),
         [(0.0, 0.52, "Rhythm masks", "Hold a groove: a grid, or an exact pattern"), (0.52, 1.0, "Remix", "Keep the rhythm, change the notes")]),
        (28, 32, "main", ("seq", "stats3", 0.0), STATS_VIEW, none, [(0.05, 1.0, "Generation stats", "Speed, time, notes, seed and attempts for every batch")]),
        (32, 34, "main", ("seq", "peakA", 0.0), PEAK_ROLL, none, [(0.0, 1.0, "Rewrite part of a track", "Select the bars: here, bars 5 to 8 of the bass")]),
        (34, 36, "main", ("seq", "peakA", 2 * T), MASK_SCALE, glows(("SCALE", 0.05, 0.4), ("ROOT", 0.25, 0.55), ("MODE", 0.45, 0.8)),
         [(0.0, 1.0, "Lock the scale", "F natural minor, in the bass register. Then generate")]),
        (36, 40, "main", ("seq", "peakB", 0.0), PEAK_ROLL, none, [(0.0, 1.0, "Same groove, new bass line", "Bars 5 to 8 rewritten in F minor")]),
        (40, 44, "engine", ("seq", "engine3", 0.0), ENGINE_WIDE, glows(("CONTEXT", 0.1, 0.4), ("BARS/STEP", 0.45, 0.8)),
         [(0.0, 1.0, "Engine", "Choose the model and how it generates")]),
        (44, 48, "setup", ("seq", "setup3", 0.0), SETUP_WIDE, none,
         [(0.0, 0.42, "Setup", "Use a server on this computer, or on another machine"), (0.42, 1.0, "Setup", "Any of the 128 General MIDI instruments, plus drums")]),
        (48, 55, "main", ("seq", "outro", 0.0), OUTRO, none, []),
    ],
    "short": [
        (2, 4, "main", ("seq", "intro", 0.0), INTRO, rise, []),
        (4, 6, "main", ("seq", "build3", 0.4, 1.4), WHOLE_HUD, glows(("POLY", 0.3, 0.6), ("TAKES", 0.6, 0.95)),
         [(0.0, 0.5, "Pick what to write", "AR writes the whole track"), (0.5, 1.0, "Ask for takes", "Several options at once")]),
        (6, 8, "main", ("seq", "press3", 0.0), GEN_WIDE, lambda t, p: press(min(1, t * 2), p) if t < 0.5 else pulse(t, p),
         [(0.5, 1.0, "Generating", "A new lead, written to fit the groove")]),
        (8, 12, "main", ("seq", "takes3", 0.0), TAKES_SWEEP, glow("TAKE1", 0.0, 0.4), [(0.05, 1.0, "Takes", "Several options from one batch. Take 1")]),
        (12, 16, "main", ("seq", "takes3", 4 * T), TAKES_SWEEP, glow("TAKE2", 0.0, 0.4), [(0.05, 1.0, "Pick the one you like", "Take 2")]),
        (16, 20, "main", ("seq", "outro", 0.0), OUTRO, none, []),
    ],
}
TITLE_CARD = {"full": (2.0, 5.6), "short": (2.0, 3.8)}
END_CARD = {"full": (48.6, 50.4), "short": (16.2, 17.4)}
LOGO = {"full": (50.4, 52.6), "short": (17.4, 19.2)}


_P = {}
_WORK = None
_CACHE = {}


def init(work):
    global _WORK
    _WORK = work
    base = os.path.join(work, "ui3", "intro", "000.png")
    for page in ("main", "engine", "setup"):
        _P[page] = Panel(base, page=page)


_IDX = {}


def load_tex(src, t_shot):
    kind = src[0]
    if kind == "seq":
        name, start = src[1], src[2]
        speed = src[3] if len(src) > 3 else 1.0
        if name not in _IDX:
            import json
            _IDX[name] = json.load(open(os.path.join(_WORK, "ui3", name, "index.json")))
        t = start + t_shot * speed
        f = _IDX[name][0][1]
        for tt, ff in _IDX[name]:
            if tt <= t + 1e-6:
                f = ff
        key = (name, f)
        path = os.path.join(_WORK, "ui3", name, f)
        if key not in _CACHE:
            if len(_CACHE) > 8:
                _CACHE.clear()
            im = Image.open(path).convert("RGB")
            _CACHE[key] = np.asarray(im.resize((1920, 1280)) if im.size != (1920, 1280) else im, np.float32) / 255.0
        return _CACHE[key]
    if kind == "still":
        key = ("still", src[1])
        path = os.path.join(_WORK, "tex", src[1] + ".png")
        crop = False
    else:
        vt = _offset(src[1]) + src[2] + (t_shot * (src[3] if len(src) > 3 else 1.0) if kind == "video" else 0.0)
        d = os.path.join(_WORK, "ui", "fr_" + src[1])
        n = len(os.listdir(d))
        idx = int(min(n, max(1, round(vt * 30) + 1)))
        key = (src[1], idx)
        path = os.path.join(d, "%05d.jpg" % idx)
        crop = False
    if key not in _CACHE:
        if len(_CACHE) > 6:
            _CACHE.clear()
        im = Image.open(path).convert("RGB")
        if im.size != (1920, 1280):
            w, h = im.size
            im = im.crop((0, h - 1280, 1920, h))
        _CACHE[key] = np.asarray(im, np.float32) / 255.0
    return _CACHE[key]


_OFF = {}


def _offset(name):
    if name not in _OFF:
        import json
        _OFF[name] = json.load(open(os.path.join(_WORK, "ui", name + ".json")))["offset"]
    return _OFF[name]


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def spaced(d, xy, text, f, fill, track, anchor="lm"):
    x, y = xy
    if anchor == "mm":
        w = sum(d.textlength(c, font=f) + track for c in text) - track
        x -= w / 2
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill, anchor="lm")
        x += d.textlength(ch, font=f) + track
    return x


def caption(img, title, sub, alpha):
    if alpha <= 0:
        return img
    W, H = img.size
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ft, fs = font("AbletonSansSmall-Bold.ttf", int(H * 0.036)), font("AbletonSansSmall-Regular.ttf", int(H * 0.028))
    x, y = int(W * 0.055), int(H * 0.80)
    tw = max(sum(d.textlength(c, font=ft) + H * 0.005 for c in title.upper()), d.textlength(sub, font=fs))
    d.rounded_rectangle([x - 18, y - int(H * 0.035), x + tw + 22, y + int(H * 0.085)], radius=6, fill=(12, 12, 12, int(185 * alpha)))
    d.rectangle([x - 18, y - int(H * 0.035), x - 13, y + int(H * 0.085)], fill=ORANGE + (int(255 * alpha),))
    spaced(d, (x, y), title.upper(), ft, (240, 240, 240, int(255 * alpha)), H * 0.005)
    d.text((x, y + int(H * 0.05)), sub, font=fs, fill=(185, 185, 185, int(255 * alpha)), anchor="lm")
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def title_layer(W, H, tw_frac=0.7):
    t = Image.open(TITLE).convert("RGBA")
    tw = int(W * tw_frac)
    t = t.resize((tw, int(t.size[1] * tw / t.size[0])), Image.LANCZOS)
    e = max(1, int(t.size[1] * 0.35))
    ramp = np.clip(np.minimum(np.arange(t.size[0]), np.arange(t.size[0])[::-1]) / e, 0, 1)[None, :]
    rampy = np.clip(np.minimum(np.arange(t.size[1]), np.arange(t.size[1])[::-1]) / e, 0, 1)[:, None]
    t.putalpha(Image.fromarray((ramp * rampy * 255).astype(np.uint8)))
    return t


def title_card(img, alpha, lines, dark=200):
    if alpha <= 0:
        return img
    W, H = img.size
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = title_layer(W, H)
    ty = int(H * 0.27)
    card.paste(t, ((W - t.size[0]) // 2, ty))
    d = ImageDraw.Draw(card)
    y = ty + t.size[1] + H * 0.06
    for i, (text, size, fill, bold) in enumerate(lines):
        f = font("AbletonSansSmall-Bold.ttf" if bold else "AbletonSansSmall-Regular.ttf", int(H * size))
        spaced(d, (W / 2, y), text, f, fill + (255,), H * 0.004 if bold else 0, anchor="mm")
        y += H * (size + 0.03)
    card.putalpha(Image.eval(card.getchannel("A"), lambda v: int(v * alpha)))
    darkl = Image.new("RGBA", (W, H), (13, 13, 13, int(dark * alpha)))
    return Image.alpha_composite(Image.alpha_composite(img.convert("RGBA"), darkl), card).convert("RGB")


def logo_frame(size, u):
    """The Metacreation Lab mark: its two pieces turn in from either side and lock together while the camera zooms in."""
    import render_ui as R
    W, H = size
    up = 2
    img = Image.new("RGB", (W * up, H * up), (12, 12, 12))
    # a soft light behind
    yy, xx = np.mgrid[0:H * up, 0:W * up].astype(np.float32)
    r = np.sqrt(((xx - W * up / 2) / (W * up * 0.5)) ** 2 + ((yy - H * up * 0.45) / (H * up * 0.6)) ** 2)
    bg = (12 + 22 * np.clip(1 - r, 0, 1) ** 2)[..., None] * np.array([1.0, 1.0, 1.02])
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    merge = smooth(u / 0.35)                       # pieces arrive
    zoom = 0.8 + 0.25 * smooth(u / 0.7)          # slow push in
    scale = H * up * 0.0028 * zoom
    cx, cy = W * up / 2, H * up * 0.44
    mark_c = np.array([52.8, 68.66])               # the mark's centre (pt)
    for k, poly in enumerate(R.LOGO_POLYS):
        pts = np.array(poly, np.float64) - mark_c
        side = -1 if k == 0 else 1
        ang = math.radians(70 * side * (1 - merge))
        rot = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        pts = pts @ rot.T
        off = np.array([side * 120 * (1 - merge), -40 * (1 - merge)])
        pts = (pts + off) * scale + [cx, cy]
        shade = int(150 + 80 * merge)
        d.polygon([tuple(p) for p in pts], fill=(shade, shade, shade))
    # a flash of orange as they lock
    flash = bump(u, 0.3, 0.5, 0.2)
    if flash > 0:
        for k, poly in enumerate(R.LOGO_POLYS):
            pts = (np.array(poly) - mark_c) * scale + [cx, cy]
            d.line([tuple(p) for p in pts] + [tuple(pts[0])], fill=(int(255 * flash), int(150 * flash), int(70 * flash)), width=max(2, int(3 * up)))
    img = img.resize((W, H), Image.LANCZOS)
    a = smooth((u - 0.35) / 0.2)
    if a > 0:
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(over)
        y = cy / up + 137.32 * scale / up * 0.62
        spaced(d2, (W / 2, y), "METACREATION LAB", font("AbletonSansSmall-Bold.ttf", int(H * 0.04)), (235, 235, 235, int(255 * a)), H * 0.012, anchor="mm")
        spaced(d2, (W / 2, y + H * 0.06), "SIMON FRASER UNIVERSITY", font("AbletonSansSmall-Regular.ttf", int(H * 0.022)), (150, 150, 150, int(255 * a)), H * 0.006, anchor="mm")
        img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    fade = smooth(u / 0.06) * smooth((1 - u) / 0.1)
    return Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8))


DRAFT = False
PLATES = None          # composite mode: the Blender clean plates (f%05d.png, plan frame numbers) instead of the draft render


def _catmull(p0, p1, p2, p3, u):
    u2, u3 = u * u, u * u * u
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)


def cam_at(cams, t):
    """Two cameras: an eased move. A keyframe list [(t, Camera), ...]: a Catmull-Rom spline through every key
    (position, target and fov), so the camera glides through the views instead of stopping at each."""
    if not isinstance(cams[0], tuple):
        return lerp_cam(cams[0], cams[1], t)
    ts = [k[0] for k in cams]
    t = min(max(t, ts[0]), ts[-1])
    i = max(0, min(len(cams) - 2, sum(1 for x in ts[1:-1] if x <= t)))
    u = (t - ts[i]) / max(1e-6, ts[i + 1] - ts[i])
    pts = [cams[max(0, i - 1)][1], cams[i][1], cams[i + 1][1], cams[min(len(cams) - 1, i + 2)][1]]
    pos = _catmull(*[c.pos for c in pts], u)
    look = _catmull(*[c.look for c in pts], u)
    fov = _catmull(*[np.float32(c.fov) for c in pts], u)
    return Camera(tuple(pos), tuple(look), float(fov))


def frame_at(cut, sec, size, i=None):
    bar = START_BAR + sec / BAR
    lb0, lb1 = LOGO[cut]
    if bar >= lb0:
        return logo_frame(size, (bar - lb0) / (lb1 - lb0))
    shots = SHOTS[cut]
    for si, sh in enumerate(shots):
        if sh[0] <= bar < sh[1] or si == len(shots) - 1:
            break
    b0, b1, page, src, cams, state, caps = sh
    t = min(1.0, (bar - b0) / (b1 - b0))
    since = (bar - b0) * BAR
    p = _P[page]
    fade = smooth(sec / 1.0) if si == 0 else 1.0
    if si > 0 and since < 0.1:
        fade *= 0.4 + 0.6 * since / 0.1
    if PLATES:
        img = Image.open(os.path.join(PLATES, "f%05d.png" % i)).convert("RGB")
        if img.size != tuple(size):
            img = img.resize(size, Image.LANCZOS)
        if fade < 1:
            img = Image.fromarray((np.asarray(img, np.float32) * fade + 0.5).astype(np.uint8))
    else:
        p.tex = load_tex(src, since)
        st = state(t, p)
        img = render(p, cam_at(cams, t), size=size, step=2 if DRAFT else 1, lift=st.get("lift"), rot=st.get("rot"), glow=st.get("glow"), fade=fade)
    shot_secs = (b1 - b0) * BAR
    for c0, c1, title, sub in caps:
        s0, s1 = c0 * shot_secs, c1 * shot_secs
        a = smooth((since - s0 - 0.15) / 0.35) * smooth((s1 - since - 0.05) / 0.3)
        img = caption(img, title, sub, a)
    tb0, tb1 = TITLE_CARD[cut]
    if tb0 <= bar < tb1:
        u = (bar - tb0) / (tb1 - tb0)
        img = title_card(img, smooth(u / 0.25) * smooth((1 - u) / 0.2),
                         [("A MULTITRACK MIDI GENERATION MACHINE", 0.036, (235, 235, 235), True),
                          ("for Ableton Live, powered by MIDI-GPT", 0.03, (170, 170, 170), False)], dark=150)
    eb0, eb1 = END_CARD[cut]
    if bar >= eb0:
        u = (bar - eb0) / (eb1 - eb0)
        img = title_card(img, smooth(u / 0.3),          # holds until the logo takes over (no gap showing the panel)
                         [("FREE  ·  OPEN SOURCE  ·  MAX FOR LIVE", 0.03, ORANGE, True),
                          ("github.com/Metacreation-Lab/midigpt-LIVE", 0.026, (170, 170, 170), False)], dark=235)
    return img


def work(args):
    i, sec, cut, size, out, draft, plates = args
    global DRAFT, PLATES
    DRAFT, PLATES = draft, plates
    path = os.path.join(out, ("f%05d.jpg" if plates else "f%05d.png") % i)   # final frames: JPEG q95 (5x smaller)
    if not os.path.exists(path):
        frame_at(cut, sec, size, i).save(path, **({"quality": 95, "subsampling": 0} if plates else {}))


def main():
    if sys.argv[1] == "plan":                    # trailer3.py plan full|short <audio.wav> <plan.json>
        return export_plan(sys.argv[2], sys.argv[3], sys.argv[4])
    cut, workdir, wav, out = sys.argv[1:5]
    args = sys.argv[5:]
    fps = int(args[args.index("--fps") + 1]) if "--fps" in args else 24
    size = tuple(int(v) for v in args[args.index("--size") + 1].split("x")) if "--size" in args else (1280, 720)
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 4
    draft = "--draft" in args                 # preview: every second texel, 854x480, 12 fps
    plates = args[args.index("--plates") + 1] if "--plates" in args else None   # composite the Blender plates (same fps)
    if draft:
        fps, size = (fps if "--fps" in args else 12), (size if "--size" in args else (854, 480))
    os.makedirs(out, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                               capture_output=True, text=True).stdout) - PREROLL[cut] * BAR
    if "--stills" in args:
        init(workdir)
        marks = [((b0 + b1) / 2 - START_BAR) * BAR for b0, b1, *_r in SHOTS[cut]]
        marks += [((TITLE_CARD[cut][0] + TITLE_CARD[cut][1]) / 2 - START_BAR) * BAR, (END_CARD[cut][0] + 1 - START_BAR) * BAR,
                  ((LOGO[cut][0] + 0.45 * (LOGO[cut][1] - LOGO[cut][0])) - START_BAR) * BAR, ((LOGO[cut][0] + 0.8 * (LOGO[cut][1] - LOGO[cut][0])) - START_BAR) * BAR]
        for k, sec in enumerate(marks):
            frame_at(cut, min(sec, dur - 0.05), size).save(os.path.join(out, "still%02d.png" % k))
        print("stills in", out)
        return
    n = int(dur * fps)
    with Pool(jobs, initializer=init, initargs=(workdir,)) as pool:
        for k, _ in enumerate(pool.imap_unordered(work, [(i, i / fps, cut, size, out, draft, plates) for i in range(n)], chunksize=4)):
            if k % 240 == 0:
                print("frame", k, "/", n, flush=True)
    mp4 = os.path.join(out, "midigpt_trailer_%s.mp4" % cut)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(out, "f%05d.jpg" if plates else "f%05d.png"),
                    "-ss", "%.4f" % (PREROLL[cut] * BAR), "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "256k", "-af", "loudnorm=I=-14:TP=-1:LRA=9", "-shortest", mp4], check=True)
    print("wrote", mp4)


# ---------------------------------------------------------------- plan export (Blender renders the clean plates from this)
def plan_at(cut, sec):
    """What the 3D frame at <sec> shows, without text or fades: section, page, panel texture, camera, part states."""
    bar = START_BAR + sec / BAR
    shots = SHOTS[cut]
    lb0 = LOGO[cut][0]
    for si, sh in enumerate(shots):
        if sh[0] <= bar < sh[1] or si == len(shots) - 1:
            break
    b0, b1, page, src, cams, state, caps = sh
    t = min(1.0, (bar - b0) / (b1 - b0))
    since = (bar - b0) * BAR
    p = _P[page]
    st = state(t, p)
    cam = cam_at(cams, t)
    tex = None
    if src[0] == "seq":
        name, start = src[1], src[2]
        speed = src[3] if len(src) > 3 else 1.0
        if name not in _IDX:
            import json
            _IDX[name] = json.load(open(os.path.join(_WORK, "ui3", name, "index.json")))
        tt = start + since * speed
        f = _IDX[name][0][1]
        for a, b in _IDX[name]:
            if a <= tt + 1e-6:
                f = b
        tex = name + "/" + f
    k = p.k
    return {"section": si, "page": page, "tex": tex, "logo": bar >= lb0,
            "cam": {"pos": [float(v) for v in cam.pos], "look": [float(v) for v in cam.look], "fov": float(cam.fov)},
            "lift": {n: float(v) * k for n, v in (st.get("lift") or {}).items()},          # texture px
            "rot": {n: float(v) for n, v in (st.get("rot") or {}).items()},                  # degrees
            "glow": {n: [float(c) for c in v] for n, v in (st.get("glow") or {}).items()}}


def export_plan(cut, wav, out, fps=24):
    import json
    init(os.path.join(ROOT, "dist", "video"))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                               capture_output=True, text=True).stdout) - PREROLL[cut] * BAR
    frames = [plan_at(cut, i / fps) for i in range(int(dur * fps))]
    sections = {}
    for i, f in enumerate(frames):
        sections.setdefault(f["section"], [i, i])[1] = i
    json.dump({"cut": cut, "fps": fps, "frames": frames, "sections": sections,
               "shots": [[s[0], s[1], s[2]] for s in SHOTS[cut]]}, open(out, "w"))
    print("plan", cut, len(frames), "frames,", len(sections), "sections ->", out)


if __name__ == "__main__":
    main()
