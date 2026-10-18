#!/usr/bin/env python3
"""
Release trailer: the 3D panel cut to a recorded performance of the Minimal Techno trailer set.

  python3 tools/video/trailer.py full|short <textures dir> <audio.wav> <out dir> [--size 1280x720] [--fps 24] [--jobs 4] [--stills]

The audio is Live's master, recorded from song bar 1 (one bar of silence); the video starts at bar 2. Shots
are placed in bars, so every cut lands on the music. Each shot shows the panel textured with a capture of
the device in that state (targets, generating, take 3 ...). --stills renders one frame per shot instead.
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
TITLE = os.path.join(ROOT, "docs", "images", "title.png")
FONTS = "/Applications/Ableton Live 11 Suite.app/Contents/App-Resources/Fonts/"
BAR = 60.0 / 126 * 4          # seconds per bar at 126 BPM
START_BAR = 2                 # the recording's bar 1 is silence


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
# places on the panel (texture px; world y = -y)
MARK = (250, -45, 0)
ROLL = (960, -300, 0)
LEAD = (1000, -380, 0)
GEN = (1714, -952, 0)
TAKES = (1720, -612, 0)
KNOBS = (1060, -720, 0)
MASKS = (960, -1210, 0)
TRACKBAY = (420, -800, 0)

ALL = None  # filled per panel: every part name


def explode(t, p, t0=0.0, t1=1.0):
    return {"lift": {n: 22 * bump(t, t0 + (t1 - t0) * (0.05 + 0.4 * p.parts[i][2][0] / 960.0), t1, 0.35) for n, i in p.names.items()}}


def knobs(t, p):
    return {"lift": {"TEMP": 16 * smooth(t / 0.25), "TAKES": 14 * smooth((t - 0.35) / 0.2)},
            "rot": {"TEMP": -90 + 120 * smooth((t - 0.1) / 0.5), "TAKES": -120 + 200 * smooth((t - 0.4) / 0.4)}}


def press(t, p):
    down = bump(t, 0.72, 0.98, 0.5)
    return {"lift": {"GENERATE": -4 * down, "KEEP": 2},
            "glow": {"GENERATE": tuple(c * smooth((t - 0.75) / 0.2) for c in (1.0, 0.55, 0.25))}}


def pause(t, p):
    pulse = 0.5 + 0.5 * math.sin(t * math.pi * 4)
    return {"lift": {"GENERATE": -2}, "glow": {"GENERATE": tuple(c * (0.3 + 0.5 * pulse) for c in (1.0, 0.55, 0.25))}}


def take(key):
    def f(t, p):
        st = {"lift": {}}
        if key:
            st["lift"][key] = 20 * bump(t, 0.0, 0.55, 0.3) + 3
            st["glow"] = {key: tuple(c * (1 - smooth(t / 0.6)) for c in (0.9, 0.9, 0.9))}
        return st
    return f


def masks(t, p):
    return {"lift": {n: 14 * bump(t, 0.05 + 0.08 * i, 0.55 + 0.08 * i, 0.3) for i, n in enumerate(("SCALE", "ROOT", "MODE", "REGISTER"))}}


def key(name):
    return lambda t, p: {"lift": {name: 12 * bump(t, 0.0, 0.7, 0.3)}, "glow": {name: (0.4, 0.4, 0.4) if t < 0.5 else (0, 0, 0)}}


def still(t, p):
    return {}


# (bar from, bar to, texture, camera a, camera b, state, caption)
SHOTS = {
    "full": [
        (2, 4, "05_intro", C((380, -640, 220), (250, -45, 0), 36), C((300, -470, 150), (250, -45, 0), 36), still, ""),
        (4, 6, "05_intro", C((150, -2700, 650), (700, -600, 0), 40), C((960, -3300, 1500), (960, -600, 0), 38), explode, ""),
        (6, 8, "01_targets", C((300, -1000, 330), (560, -330, 0), 42), C((1400, -1000, 330), (1500, -360, 0), 42), still, "Pick a track to write"),
        (8, 10, "01_targets", C((700, -1350, 400), (980, -720, 0), 40), C((900, -1200, 330), (1060, -720, 0), 40), knobs, "Shape the sampling"),
        (10, 11, "01_targets", C((1450, -1650, 520), (1714, -950, 0), 40), C((1560, -1420, 400), (1714, -952, 0), 38), press, ""),
        (11, 12, "02_generating_b", C((1560, -1420, 400), (1714, -952, 0), 38), C((1610, -1330, 340), (1714, -900, 0), 37), pause, "Generating"),
        (12, 16, "04_take3", C((420, -1250, 520), (900, -380, 0), 44), C((1500, -1150, 480), (1300, -400, 0), 44), take("TAKE3"), "A new lead, from nothing"),
        (16, 20, "04_take6", C((1900, -1150, 500), (1200, -420, 0), 42), C((700, -1050, 420), (800, -380, 0), 42), take(None), "Take 6"),
        (20, 24, "04_take4", C((1350, -1250, 600), (1720, -560, 0), 40), C((1100, -1100, 480), (1300, -420, 0), 42), take("TAKE4"), "Take 4"),
        (24, 28, "06_peak", C((300, -1800, 420), (520, -1180, 0), 40), C((1250, -820, 480), (900, -200, 0), 42), masks, "Rewrite the bass, in key"),
        (28, 29, "08_engine", C((800, -1500, 650), (900, -760, 0), 40), C((900, -1400, 560), (900, -760, 0), 39), key("ENGINE"), "Engine"),
        (29, 30, "08_setup", C((600, -1450, 650), (700, -760, 0), 40), C((700, -1350, 560), (700, -760, 0), 39), key("SETUP"), "Setup"),
        (30, 31, "06_peak", C((600, -1700, 380), (800, -1200, 0), 40), C((900, -1650, 340), (1000, -1200, 0), 39), masks, "Masks"),
        (31, 32, "03_take1", C((1500, -1300, 500), (1720, -700, 0), 40), C((1600, -1200, 420), (1720, -700, 0), 39), take("TAKE1"), "Takes"),
        (32, 38, "07_outro", C((960, -1250, 1600), (960, -640, 0), 40), C((960, -1700, 3900), (960, -700, 0), 38), still, ""),
    ],
    "short": [
        (2, 4, "05_intro", C((150, -2700, 650), (700, -600, 0), 40), C((960, -3300, 1500), (960, -600, 0), 38), explode, ""),
        (4, 6, "01_targets", C((300, -1000, 330), (560, -330, 0), 42), C((1400, -1000, 330), (1500, -360, 0), 42), still, "Pick a track to write"),
        (6, 7, "01_targets", C((1450, -1650, 520), (1714, -950, 0), 40), C((1560, -1420, 400), (1714, -952, 0), 38), press, ""),
        (7, 8, "02_generating_b", C((1560, -1420, 400), (1714, -952, 0), 38), C((1610, -1330, 340), (1714, -900, 0), 37), pause, "Generating"),
        (8, 12, "04_take3", C((420, -1250, 520), (900, -380, 0), 44), C((1500, -1150, 480), (1300, -400, 0), 44), take("TAKE3"), "A new lead, from nothing"),
        (12, 16, "04_take6", C((1900, -1150, 500), (1200, -420, 0), 42), C((700, -1050, 420), (800, -380, 0), 42), take(None), "Another take"),
        (16, 20, "07_outro", C((960, -1250, 1600), (960, -640, 0), 40), C((960, -1700, 3900), (960, -700, 0), 38), still, ""),
    ],
}
END_CARD_BAR = {"full": 33.0, "short": 16.5}


_P = None
_TEX = {}


def init(texdir):
    global _P
    _P = Panel(os.path.join(texdir, "01_targets.png"))
    for f in os.listdir(texdir):
        if f.endswith(".png"):
            _TEX[f[:-4]] = np.asarray(Image.open(os.path.join(texdir, f)).convert("RGB"), np.float32) / 255.0


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def caption(img, text, alpha):
    if not text or alpha <= 0:
        return img
    W, H = img.size
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    f = font("AbletonSansSmall-Bold.ttf", int(H * 0.034))
    x, y = int(W * 0.05), int(H * 0.88)
    tw = d.textlength(text.upper(), font=f) + len(text) * H * 0.006
    d.rectangle([x - 14, y - int(H * 0.03), x + tw + 14, y + int(H * 0.03)], fill=(10, 10, 10, int(150 * alpha)))
    d.rectangle([x - 14, y - int(H * 0.03), x - 10, y + int(H * 0.03)], fill=(255, 150, 70, int(255 * alpha)))
    cx = x
    for ch in text.upper():                       # letter-spaced, like the panel's legends
        d.text((cx, y), ch, font=f, fill=(235, 235, 235, int(255 * alpha)), anchor="lm")
        cx += d.textlength(ch, font=f) + H * 0.006
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def end_card(img, alpha):
    if alpha <= 0:
        return img
    W, H = img.size
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = Image.open(TITLE).convert("RGBA")
    tw = int(W * 0.74)
    t = t.resize((tw, int(t.size[1] * tw / t.size[0])), Image.LANCZOS)
    e = max(1, int(t.size[1] * 0.35))
    ramp = np.clip(np.minimum(np.arange(t.size[0]), np.arange(t.size[0])[::-1]) / e, 0, 1)[None, :]
    rampy = np.clip(np.minimum(np.arange(t.size[1]), np.arange(t.size[1])[::-1]) / e, 0, 1)[:, None]
    t.putalpha(Image.fromarray((ramp * rampy * 255).astype(np.uint8)))
    ty = int(H * 0.28)
    card.paste(t, ((W - tw) // 2, ty))
    d = ImageDraw.Draw(card)
    f1 = font("AbletonSansSmall-Bold.ttf", int(H * 0.03))
    f2 = font("AbletonSansSmall-Regular.ttf", int(H * 0.026))
    y = ty + t.size[1] + H * 0.07
    d.text((W / 2, y), "FREE  ·  OPEN SOURCE  ·  MAX FOR LIVE", font=f1, fill=(255, 150, 70, 255), anchor="mm")
    d.text((W / 2, y + H * 0.06), "github.com/Metacreation-Lab/midigpt-LIVE", font=f2, fill=(170, 170, 170, 255), anchor="mm")
    card.putalpha(Image.eval(card.getchannel("A"), lambda v: int(v * alpha)))
    dark = Image.new("RGBA", (W, H), (13, 13, 13, int(245 * alpha)))
    return Image.alpha_composite(Image.alpha_composite(img.convert("RGBA"), dark), card).convert("RGB")


def frame_at(cut, sec, size):
    """The frame at <sec> seconds into the video."""
    bar = START_BAR + sec / BAR
    shots = SHOTS[cut]
    for si, (b0, b1, tex, a, b, state, cap) in enumerate(shots):
        if b0 <= bar < b1 or si == len(shots) - 1:
            break
    t = min(1.0, (bar - b0) / (b1 - b0))
    _P.tex = _TEX[tex]
    st = state(t, _P)
    # fade in at the very start, a short dip at each cut, fade out at the end
    fade = 1.0
    if si == 0:
        fade = smooth(sec / 0.8)
    since = (bar - b0) * BAR
    if si > 0 and since < 0.08:
        fade *= 0.35 + 0.65 * since / 0.08
    cam = lerp_cam(a, b, t)
    img = render(_P, cam, size=size, lift=st.get("lift"), rot=st.get("rot"), glow=st.get("glow"), fade=fade)
    shot_secs = (b1 - b0) * BAR
    cap_alpha = smooth((since - 0.15) / 0.3) * smooth((shot_secs - since - 0.1) / 0.3) if cap else 0
    img = caption(img, cap, cap_alpha)
    eb = END_CARD_BAR[cut]
    if bar >= eb:
        img = end_card(img, smooth((bar - eb) / 1.2))
    return img


def work(args):
    i, sec, cut, size, out = args
    path = os.path.join(out, "f%05d.png" % i)
    if not os.path.exists(path):
        frame_at(cut, sec, size).save(path)


def main():
    cut, texdir, wav, out = sys.argv[1:5]
    args = sys.argv[5:]
    fps = int(args[args.index("--fps") + 1]) if "--fps" in args else 24
    size = tuple(int(v) for v in args[args.index("--size") + 1].split("x")) if "--size" in args else (1280, 720)
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 4
    os.makedirs(out, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                               capture_output=True, text=True).stdout) - (START_BAR - 1) * BAR
    if "--stills" in args:
        init(texdir)
        for si, (b0, b1, tex, *_r) in enumerate(SHOTS[cut]):
            mid = ((b0 + b1) / 2 - START_BAR) * BAR
            frame_at(cut, min(mid, dur - 0.1), size).save(os.path.join(out, "shot%02d.png" % si))
        print("stills in", out)
        return
    n = int(dur * fps)
    with Pool(jobs, initializer=init, initargs=(texdir,)) as pool:
        for k, _ in enumerate(pool.imap_unordered(work, [(i, i / fps, cut, size, out) for i in range(n)], chunksize=4)):
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
