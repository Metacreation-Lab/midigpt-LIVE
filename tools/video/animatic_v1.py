#!/usr/bin/env python3
"""
Release video, version 1: a 70 s animatic of "the panel comes apart" (no sound yet).

  python3 tools/video/animatic_v1.py <panel texture.png> <out dir> [--fps 24] [--size 1280x720] [--jobs 10]

Renders every frame with tools/video/panel3d.py in parallel, then encodes <out dir>/midigpt_v1.mp4.
"""

import math
import os
import subprocess
import sys
from multiprocessing import Pool

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from panel3d import Camera, Panel, lerp_cam, render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TITLE = os.path.join(ROOT, "docs", "images", "title.png")
FONT = "/Applications/Ableton Live 11 Suite.app/Contents/App-Resources/Fonts/AbletonSansSmall-Bold.ttf"


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def bump(t, t0, t1, hold=0.35):
    """0 -> 1 -> 0 between t0 and t1, with a hold in the middle."""
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
SHOTS = [
    # name, seconds, camera start, camera end, state(t, panel) -> dict(lift, rot, glow)
    ("mark", 4, C((380, -640, 220), (250, -45, 0), 36), C((300, -470, 150), (250, -45, 0), 36),
     lambda t, p: {}),
    ("explode", 6, C((150, -2700, 650), (700, -600, 0), 40), C((960, -3300, 1500), (960, -600, 0), 38),
     lambda t, p: {"lift": {n: 26 * bump(t, 0.05 + 0.25 * (p.parts[i][2][0] / 960.0), 0.98, 0.3) for n, i in p.names.items()}}),
    ("roll", 8, C((300, -900, 320), (520, -250, 0), 42), C((1500, -900, 320), (1640, -250, 0), 42),
     lambda t, p: {}),
    ("paint", 6, C((780, -950, 340), (1040, -250, 0), 42), C((920, -760, 240), (1120, -300, 0), 40),
     lambda t, p: {}),
    ("shape", 10, C((640, -1300, 420), (880, -660, 0), 40), C((900, -1180, 360), (1000, -660, 0), 40),
     lambda t, p: {"lift": {"TEMP": 18 * smooth((t - 0.1) / 0.15), "TOP-P": 12 * smooth((t - 0.45) / 0.15),
                            "TOP-K": 6 * smooth((t - 0.6) / 0.15)},
                   "rot": {"TEMP": -110 + 170 * smooth((t - 0.25) / 0.45), "TOP-P": -60 + 90 * smooth((t - 0.6) / 0.3)}}),
    ("masks", 8, C((300, -1700, 380), (500, -1150, 0), 40), C((1350, -1700, 380), (1350, -1150, 0), 40),
     lambda t, p: {"lift": {n: 16 * bump(t, 0.05 + 0.6 * (p.parts[p.names[n]][2][0] / 960.0), 0.05 + 0.6 * (p.parts[p.names[n]][2][0] / 960.0) + 0.35)
                            for n in ("SCALE", "ROOT", "MODE", "REGISTER", "RHYTHM", "UNIT", "STRENGTH", "REMIX", "AMOUNT", "P+D")}}),
    ("generate", 8, C((1250, -1720, 540), (1600, -960, 0), 40), C((1390, -1540, 420), (1660, -960, 0), 38),
     lambda t, p: {"lift": {"GENERATE": -3 * bump(t, 0.32, 0.5, 0.2), "KEEP": 2},
                   "glow": {"GENERATE": tuple(c * (0.5 + 0.5 * math.sin((t - 0.45) * 18)) * (t > 0.45) for c in (1.0, 0.6, 0.3))}}),
    ("takes", 6, C((1230, -1180, 540), (1640, -620, 0), 40), C((1300, -1120, 480), (1680, -620, 0), 40),
     lambda t, p: {"lift": dict([("TAKE%d" % i, 22 * bump(t, 0.08 + 0.13 * i, 0.08 + 0.13 * i + 0.3, 0.2)) for i in range(5)] +
                                [("KEEP", -3 * bump(t, 0.8, 0.95, 0.2))])}),
    ("topkeys", 6, C((1250, -560, 320), (1700, -20, 0), 40), C((1500, -470, 260), (1760, -20, 0), 38),
     lambda t, p: {"lift": {"ENGINE": 14 * bump(t, 0.15, 0.7), "SETUP": 14 * bump(t, 0.35, 0.9)},
                   "glow": {"ENGINE": (0.5, 0.5, 0.5) if 0.3 < t < 0.6 else (0, 0, 0), "SETUP": (0.5, 0.5, 0.5) if 0.5 < t < 0.8 else (0, 0, 0)}}),
    ("outro", 8, C((960, -1250, 1600), (960, -640, 0), 40), C((960, -1700, 3900), (960, -700, 0), 38),
     lambda t, p: {}),
]


def timeline(fps):
    frames = []
    for si, (name, secs, a, b, state) in enumerate(SHOTS):
        n = int(secs * fps)
        for f in range(n):
            frames.append((si, f, n))
    return frames


_P = None


def init(tex):
    global _P
    _P = Panel(tex)


def end_card(img, alpha):
    """The title banner and the install line over the last seconds."""
    if alpha <= 0:
        return img
    W, H = img.size
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = Image.open(TITLE).convert("RGBA")
    tw = int(W * 0.78)
    t = t.resize((tw, int(t.size[1] * tw / t.size[0])), Image.LANCZOS)
    # feather the banner's edges into the backdrop
    import numpy as np
    a_ = np.ones((t.size[1], t.size[0]), np.float32)
    e = max(1, int(t.size[1] * 0.35))
    ramp = np.clip(np.minimum(np.arange(t.size[0]), np.arange(t.size[0])[::-1]) / e, 0, 1)[None, :]
    rampy = np.clip(np.minimum(np.arange(t.size[1]), np.arange(t.size[1])[::-1]) / e, 0, 1)[:, None]
    t.putalpha(Image.fromarray((a_ * ramp * rampy * 255).astype(np.uint8)))
    card.paste(t, ((W - tw) // 2, int(H * 0.30)))
    d = ImageDraw.Draw(card)
    f = ImageFont.truetype(FONT, int(H * 0.026))
    line = "curl -fsSL metacreation.net/MIDI-GPT/bootstrap.sh | bash"
    d.text((W / 2, H * 0.30 + t.size[1] + H * 0.06), line, font=f, fill=(170, 170, 170, 255), anchor="mm")
    card.putalpha(Image.eval(card.getchannel("A"), lambda v: int(v * alpha)))
    base = img.convert("RGBA")
    dark = Image.new("RGBA", (W, H), (13, 13, 13, int(250 * alpha)))
    return Image.alpha_composite(Image.alpha_composite(base, dark), card).convert("RGB")


def work(args):
    i, (si, f, n), size, out = args
    path = os.path.join(out, "f%05d.png" % i)
    if os.path.exists(path):
        return
    name, secs, a, b, state = SHOTS[si]
    t = f / max(1, n - 1)
    cam = lerp_cam(a, b, t)
    st = state(t, _P)
    # dips through black at the cuts (fade in from black at the start)
    k = 5 if si else 30
    fade = min(1.0, (f + 1) / k, (n - f) / 5.0)
    img = render(_P, cam, size=size, lift=st.get("lift"), rot=st.get("rot"), glow=st.get("glow"), fade=fade)
    if name == "outro":
        img = end_card(img, smooth((t - 0.45) / 0.3))
    img.save(path)


def main():
    tex, out = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    fps = int(args[args.index("--fps") + 1]) if "--fps" in args else 24
    size = tuple(int(v) for v in args[args.index("--size") + 1].split("x")) if "--size" in args else (1280, 720)
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 10
    os.makedirs(out, exist_ok=True)
    tl = timeline(fps)
    with Pool(jobs, initializer=init, initargs=(tex,)) as pool:
        for k, _ in enumerate(pool.imap_unordered(work, [(i, fr, size, out) for i, fr in enumerate(tl)], chunksize=4)):
            if k % 120 == 0:
                print("frame", k, "/", len(tl), flush=True)
    mp4 = os.path.join(out, "midigpt_v1.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(out, "f%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", mp4], check=True)
    print("wrote", mp4)


if __name__ == "__main__":
    main()
