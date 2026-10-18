#!/usr/bin/env python3
"""
Release trailer v2: the 3D panel, textured with screen recordings of the device performing each step, cut to a
recorded performance of the Minimal Techno trailer set.

  python3 tools/video/trailer2.py full|short <work dir> <audio.wav> <out dir> [--size 1280x720] [--fps 24] [--jobs 4] [--stills] [--draft]

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
# calm, mostly frontal views (texture px; world y = -y)
WHOLE = (C((960, -1500, 1750), (960, -640, 0), 40), C((960, -1420, 1640), (960, -630, 0), 40))
ROLL_LEAD = (C((900, -1000, 980), (980, -420, 0), 38), C((1040, -980, 940), (1040, -420, 0), 38))
SAMPLE_OUT = (C((1250, -1250, 900), (1250, -720, 0), 38), C((1300, -1220, 860), (1300, -720, 0), 37))
GEN_CLOSE = (C((1600, -1350, 760), (1650, -900, 0), 36), C((1640, -1300, 700), (1670, -910, 0), 35))
TOP_HALF = (C((1220, -1250, 1500), (1220, -520, 0), 42), C((1260, -1230, 1460), (1260, -520, 0), 42))
PEAK_VIEW = (C((900, -1050, 1200), (960, -330, 0), 40), C((980, -1020, 1150), (980, -330, 0), 40))
ENGINE_BAY = (C((600, -1500, 1500), (620, -740, 0), 42), C((640, -1480, 1460), (640, -740, 0), 42))
SETUP_BAY = (C((700, -1500, 1500), (700, -740, 0), 42), C((660, -1480, 1460), (660, -740, 0), 42))
OUTRO = (C((960, -1400, 1700), (960, -640, 0), 40), C((960, -1800, 3600), (960, -700, 0), 38))
INTRO = (C((960, -2600, 2700), (960, -600, 0), 40), C((960, -1500, 1750), (960, -640, 0), 40))


def rise(t, p):
    """The parts lift gently out of the plate, left to right, and settle."""
    return {"lift": {n: 10 * bump(t, 0.1 + 0.4 * p.parts[i][2][0] / 960.0, 0.95, 0.4) for n, i in p.names.items()}}


def glow(name, t0=0.0, t1=1.0, lift=8):
    def f(t, p):
        if name not in p.names:
            return {}
        a = bump(t, t0, t1, 0.6)
        return {"lift": {name: 4 * a}, "glow": {name: (0.12 * a, 0.08 * a, 0.03 * a)}}
    return f


def glows(*items):
    """items: (name, t0, t1) — several highlights over one shot."""
    def f(t, p):
        st = {"lift": {}, "glow": {}}
        for name, t0, t1 in items:
            if name in p.names:
                a = bump(t, t0, t1, 0.6)
                st["lift"][name] = max(st["lift"].get(name, 0), 4 * a)
                st["glow"][name] = (0.12 * a, 0.08 * a, 0.03 * a)
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


T = BAR  # seconds per bar, for the video-time offsets below
# shot: (bar from, bar to, page, source, cameras, state, captions)
#   source: ("still", name) | ("video", recording, video time at the shot's start) | ("freeze", recording, video time)
#   captions: [(t0, t1, title, subtitle)] in shot fractions
SHOTS = {
    "full": [
        (2, 6, "main", ("still", "05_intro"), INTRO, rise, []),
        (6, 8, "main", ("video", "build", 0.0), ROLL_LEAD, none, [(0.0, 1.0, "Pick what to write", "Paint the bars to generate. Here: an empty lead track")]),
        (8, 10, "main", ("video", "build", 2.6), SAMPLE_OUT, glow("TAKES", 0.05, 0.75), [(0.0, 1.0, "Ask for takes", "One click, several options")]),
        (10, 11, "main", ("freeze", "press", 3.0), GEN_CLOSE, press, []),
        (11, 12, "main", ("video", "press", 8.5), GEN_CLOSE, pulse, [(0.0, 1.0, "Generating", "MIDI-GPT listens to every track and writes a new one")]),
        (12, 16, "main", ("video", "takes", 3.70), TOP_HALF, glow("TAKE1", 0.0, 0.5), [(0.05, 1.0, "Takes", "Four new lead lines from one batch. This is take 1")]),
        (16, 20, "main", ("video", "takes", 3.70 + 4 * T), TOP_HALF, glow("TAKE4", 0.0, 0.5), [(0.05, 1.0, "Pick the one you like", "Take 4")]),
        (20, 24, "main", ("video", "takes", 3.70 + 8 * T), TOP_HALF, glow("TAKE2", 0.0, 0.5), [(0.05, 1.0, "Switch any time", "Take 2. Keep commits it, back-arrow restores the original")]),
        (24, 28, "main", ("video", "peakA", 0.96), PEAK_VIEW, glow("SCALE", 0.3, 0.75), [(0.0, 1.0, "Rewrite part of a track", "Select bars, lock the scale, generate")]),
        (28, 32, "main", ("video", "peakB", 4.6), PEAK_VIEW, none, [(0.0, 1.0, "Same groove, new bass line", "Bars 5 to 8 rewritten in F minor")]),
        (32, 40, "engine", ("video", "engine", 0.98), ENGINE_BAY,
         glows(("CONTEXT", 0.1, 0.3), ("BARS/STEP", 0.28, 0.48), ("ATTEMPTS", 0.48, 0.66), ("MASK P", 0.66, 0.9)),
         [(0.0, 0.5, "Engine", "Choose the model"), (0.5, 1.0, "Engine", "and how it generates: context, bars per step, attempts")]),
        (40, 48, "setup", ("video", "setup", 1.42), SETUP_BAY, none,
         [(0.0, 0.5, "Setup", "Give every track an instrument"), (0.5, 1.0, "Setup", "Any of the 128 General MIDI instruments, plus drums")]),
        (48, 54, "main", ("still", "07_outro"), OUTRO, none, []),
    ],
    "short": [
        (2, 4, "main", ("still", "05_intro"), INTRO, rise, []),
        (4, 6, "main", ("video", "build", 0.6), TOP_HALF, glow("TAKES", 0.55, 0.95), [(0.0, 0.5, "Pick what to write", "An empty lead track"), (0.5, 1.0, "Ask for takes", "Several options at once")]),
        (6, 7, "main", ("freeze", "press", 3.0), GEN_CLOSE, press, []),
        (7, 8, "main", ("video", "press", 8.5), GEN_CLOSE, pulse, [(0.0, 1.0, "Generating", "A new lead, written to fit the groove")]),
        (8, 12, "main", ("video", "takes", 3.70), TOP_HALF, glow("TAKE1", 0.0, 0.5), [(0.05, 1.0, "Takes", "Four options from one batch. Take 1")]),
        (12, 16, "main", ("video", "takes", 3.70 + 4 * T), TOP_HALF, glow("TAKE4", 0.0, 0.5), [(0.05, 1.0, "Pick the one you like", "Take 4")]),
        (16, 20, "main", ("still", "07_outro"), OUTRO, none, []),
    ],
}
TITLE_CARD = {"full": (2.0, 5.6), "short": (2.0, 3.8)}         # bars: the opening title over the intro
END_CARD = {"full": (48.5, 51.0), "short": (16.2, 17.6)}        # bars: title + install line
LOGO = {"full": (51.0, 55.0), "short": (17.6, 20.0)}            # bars: the Metacreation Lab mark assembles

_P = {}
_WORK = None
_CACHE = {}


def init(work):
    global _WORK
    _WORK = work
    base = os.path.join(work, "tex", "05_intro.png")
    for page in ("main", "engine", "setup"):
        _P[page] = Panel(base, page=page)


def load_tex(src, t_shot):
    kind = src[0]
    if kind == "still":
        key = ("still", src[1])
        path = os.path.join(_WORK, "tex", src[1] + ".png")
        crop = False
    else:
        vt = src[2] + (t_shot if kind == "video" else 0.0)
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
    merge = smooth(u / 0.55)                       # pieces arrive
    zoom = 0.75 + 0.45 * smooth(u / 0.85)          # slow push in
    scale = H * up * 0.0042 * zoom
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
    flash = bump(u, 0.5, 0.75, 0.2)
    if flash > 0:
        for k, poly in enumerate(R.LOGO_POLYS):
            pts = (np.array(poly) - mark_c) * scale + [cx, cy]
            d.line([tuple(p) for p in pts] + [tuple(pts[0])], fill=(int(255 * flash), int(150 * flash), int(70 * flash)), width=max(2, int(3 * up)))
    img = img.resize((W, H), Image.LANCZOS)
    a = smooth((u - 0.55) / 0.25)
    if a > 0:
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(over)
        y = cy / up + 137.32 * scale / up * 0.62
        spaced(d2, (W / 2, y), "METACREATION LAB", font("AbletonSansSmall-Bold.ttf", int(H * 0.04)), (235, 235, 235, int(255 * a)), H * 0.012, anchor="mm")
        spaced(d2, (W / 2, y + H * 0.06), "SIMON FRASER UNIVERSITY", font("AbletonSansSmall-Regular.ttf", int(H * 0.022)), (150, 150, 150, int(255 * a)), H * 0.006, anchor="mm")
        img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    fade = smooth(u / 0.08) * smooth((1 - u) / 0.12)
    return Image.fromarray((np.asarray(img, np.float32) * fade).astype(np.uint8))


DRAFT = False


def frame_at(cut, sec, size):
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
    p.tex = load_tex(src, since)
    st = state(t, p)
    fade = smooth(sec / 1.0) if si == 0 else 1.0
    if si > 0 and since < 0.1:
        fade *= 0.4 + 0.6 * since / 0.1
    img = render(p, lerp_cam(cams[0], cams[1], t), size=size, step=2 if DRAFT else 1, lift=st.get("lift"), rot=st.get("rot"), glow=st.get("glow"), fade=fade)
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
        img = title_card(img, smooth(u / 0.3) * smooth((1 - u) / 0.12) if bar < eb1 else 0,
                         [("FREE  ·  OPEN SOURCE  ·  MAX FOR LIVE", 0.03, ORANGE, True),
                          ("github.com/Metacreation-Lab/midigpt-LIVE", 0.026, (170, 170, 170), False)], dark=235)
    return img


def work(args):
    i, sec, cut, size, out, draft = args
    global DRAFT
    DRAFT = draft
    path = os.path.join(out, "f%05d.png" % i)
    if not os.path.exists(path):
        frame_at(cut, sec, size).save(path)


def main():
    cut, workdir, wav, out = sys.argv[1:5]
    args = sys.argv[5:]
    fps = int(args[args.index("--fps") + 1]) if "--fps" in args else 24
    size = tuple(int(v) for v in args[args.index("--size") + 1].split("x")) if "--size" in args else (1280, 720)
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 4
    draft = "--draft" in args                 # preview: every second texel, 854x480, 12 fps
    if draft:
        fps, size = (fps if "--fps" in args else 12), (size if "--size" in args else (854, 480))
    os.makedirs(out, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                               capture_output=True, text=True).stdout) - (START_BAR - 1) * BAR
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
        for k, _ in enumerate(pool.imap_unordered(work, [(i, i / fps, cut, size, out, draft) for i in range(n)], chunksize=4)):
            if k % 240 == 0:
                print("frame", k, "/", n, flush=True)
    mp4 = os.path.join(out, "midigpt_trailer_%s.mp4" % cut)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(out, "f%05d.png"),
                    "-ss", "%.4f" % ((START_BAR - 1) * BAR), "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "256k", "-af", "loudnorm=I=-14:TP=-1:LRA=9", "-shortest", mp4], check=True)
    print("wrote", mp4)


if __name__ == "__main__":
    main()
