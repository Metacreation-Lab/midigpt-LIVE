#!/usr/bin/env python3
"""
Export the assets for the interactive front end (and later the jsui device):
one background per page (panel, bays, screen pockets, toggle slots, logo) and
transparent sprites for every raised part (knob bodies, keys, toggle thumbs)
with their soft shadows baked in as alpha. Everything that changes at runtime
(LED rings, pointers, legends, labels, screens) is drawn by the front end.

Shadows become alpha by rendering each part twice, with and without the part:
where the part is, the pixel is the part; elsewhere the darkening becomes black
with alpha = 1 - lit/unlit.

  python3 tools/frontend_assets.py <out_dir>
"""

import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_ui as R  # noqa: E402
import button_studies as B  # noqa: E402
import layouts as LY  # noqa: E402

S = R.S
ST = R.STYLES["cockpit"]
LVL = LY.LVL


# ---------------------------------------------------------------- page specs (Max points, 960 x 640)
TOP_KEYS = [("ENGINE", 798, 9, 70, 22), ("SETUP", 874, 9, 70, 22)]
SCREEN = (12, 44, 936, 206)
# OUTPUT, top to bottom: take keys with their group keys right under them (one unit), the stats screen, Keep / Generate
OUTPUT = dict(bay=(694, 264, 254, 252, "OUTPUT"),
              takes=[(710 + i * 44, 288, 38, 38) for i in range(5)],
              pages=[(754 + i * 44, 333, 38, 8) for i in range(4)],   # thin LED-only keys: which group of 4 takes
              stats=(712, 359, 218, 76),
              keep=(710, 453, 64, 46), generate=(782, 453, 150, 46))
# MASKS: pitch group | rhythm group (a small HUD screen edits the rhythm, so any grid unit / time signature fits) | remix group
EXTRAS = dict(bay=(12, 528, 936, 100, "MASKS"),
              toggles=[("SCALE", 36, 576, 44, 16), ("RHYTHM", 300, 576, 44, 16), ("REMIX", 772, 576, 44, 16), ("P+D", 898, 576, 36, 16)],
              knobs=[("ROOT", 120, 578, 13), ("MODE", 180, 578, 13), ("REGISTER", 244, 578, 13),
                     ("UNIT", 384, 578, 13), ("STRENGTH", 732, 578, 13), ("AMOUNT", 852, 578, 13)],
              steps=None, rhythm=(412, 552, 290, 58))

# Rows are centred in each section: a knob of radius r spans r*1.24+1.5 above its centre and r*1.3+24 below
# (ring, label, value); a toggle spans 13 above its top and 19 below.
PAGES = {
    "main": dict(
        bays=[(12, 264, 372, 252, "TRACK"), (394, 264, 290, 252, "SAMPLE")],
        knobs=[("POLY", 74, 343, 26), ("LENGTH", 198, 343, 26), ("TRACK TEMP", 322, 343, 26), ("DENSITY", 136, 343, 26),
               ("KEY", 58, 445, 14), ("RANGE", 151, 445, 14), ("SILENCE", 244, 445, 14), ("PCS", 337, 445, 14),
               ("TEMP", 442, 327, 22), ("TOP-P", 539, 327, 22), ("TOP-K", 636, 327, 22),
               ("ESC", 424, 412, 15), ("TAKES", 484, 412, 15), ("PROB", 544, 412, 15), ("SEED", 628, 412, 15)],
        toggles=[("NOVELTY", 420, 481, 44, 16), ("SILENCE CHK", 517, 481, 44, 16), ("SHUFFLE", 614, 481, 44, 16)],
        keys=[], screens=[]),
    # ENGINE for models that cannot switch velocity / microtiming: no toggles, the model list centred
    "engine": dict(
        bays=[(12, 264, 672, 252, "ENGINE")],
        knobs=[("CONTEXT", 64, 340, 20), ("BARS/STEP", 164, 340, 20), ("TRK/STEP", 264, 340, 20), ("ATTEMPTS", 364, 340, 20),
               ("POLY LIM", 64, 432, 20), ("DENS LIM", 164, 432, 20), ("MASK P", 264, 432, 20), ("MASK K", 364, 432, 20)],
        toggles=[],
        keys=[],
        screens=[("models", 436, 308, 228, 180)]),
    # ENGINE for models that can: the model list and the two toggles, centred together
    "engine_vm": dict(
        bays=[(12, 264, 672, 252, "ENGINE")],
        knobs=[("CONTEXT", 64, 340, 20), ("BARS/STEP", 164, 340, 20), ("TRK/STEP", 264, 340, 20), ("ATTEMPTS", 364, 340, 20),
               ("POLY LIM", 64, 432, 20), ("DENS LIM", 164, 432, 20), ("MASK P", 264, 432, 20), ("MASK K", 364, 432, 20)],
        toggles=[("VELOCITY", 482, 480, 44, 16), ("MICRO", 574, 480, 44, 16)],
        keys=[],
        screens=[("models", 436, 296, 228, 150)]),
    # SETUP: server line + track list on the left; setup keys and the instrument browser (a HUD list, not knobs) on the right
    "setup": dict(
        bays=[(12, 264, 672, 252, "SETUP")],
        knobs=[],
        toggles=[],
        keys=[("CONNECT", 372, 292, 68, 28), ("SETUP ALL", 446, 292, 68, 28), ("SETUP SEL", 520, 292, 68, 28), ("RESET", 594, 292, 68, 28)],
        screens=[("server", 32, 292, 320, 28), ("tracks", 32, 332, 320, 168), ("browser", 372, 332, 290, 168)]),
}


def all_sizes():
    knobs, keys, thumbs = set(), set(), set()
    for p in PAGES.values():
        for k in p["knobs"]:
            knobs.add(k[3])
        for t in p["toggles"]:
            thumbs.add((t[3], t[4]))
        for kk in p["keys"]:
            keys.add((kk[3], kk[4]))
    for k in EXTRAS["knobs"]:
        knobs.add(k[3])
    for t in EXTRAS["toggles"]:
        thumbs.add((t[3], t[4]))
    for (_, x, y, w, h) in TOP_KEYS:
        keys.add((w, h))
    for (x, y, w, h) in OUTPUT["takes"] + OUTPUT["pages"]:
        keys.add((w, h))
    keys.add(OUTPUT["keep"][2:])
    keys.add(OUTPUT["generate"][2:])
    if EXTRAS["steps"]:
        keys.add((EXTRAS["steps"][3], EXTRAS["steps"][4]))
    return sorted(knobs), sorted(keys), sorted(thumbs)


# ---------------------------------------------------------------- backgrounds
def slot(c, x, y, w, h, level):
    sh = h * 0.8
    c.rrect(x * S, (y + h / 2 - sh / 2) * S, w * S, sh * S, sh / 2 * S, 1.8 * S, 0.4 * S, "chamfer", R.P["track"], R.MATTE, level, sink=True)


def screen_pocket(c, x, y, w, h, big=False):
    pad, dep = (5, 2.6) if big else (4, 2.2)
    c.rrect((x - pad) * S, (y - pad) * S, (w + 2 * pad) * S, (h + 2 * pad) * S, (8 + pad) * S, dep * S, 0.5 * S, "chamfer",
            R.P["plate"], R.MATTE, LVL, sink=True)
    c.rrect(x * S, y * S, w * S, h * S, 7 * S, 0.8 * S, 0.6 * S, "round", R.P["screen"], (30, 0.0, 0), LVL - dep * S)


def background(page):
    p = PAGES[page]
    c = R.Canvas(960 * S, 640 * S, R.P["base"], R.MATTE)
    R.engrave_logo(c)
    for (x, y, w, h, _) in p["bays"] + [OUTPUT["bay"], EXTRAS["bay"]]:
        c.rrect(x * S, y * S, w * S, h * S, 12 * S, 1.2 * S, 3.0 * S, "trench", R.P["plate"], R.MATTE, 0, sink=True)
    screen_pocket(c, *SCREEN, big=True)
    screen_pocket(c, *OUTPUT["stats"])
    screen_pocket(c, *EXTRAS["rhythm"])
    for (_, x, y, w, h) in p["screens"]:
        screen_pocket(c, x, y, w, h)
    for (_, x, y, w, h) in p["toggles"] + EXTRAS["toggles"]:
        slot(c, x, y, w, h, LVL)
    img = c.shade(ST)
    return Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")


# ---------------------------------------------------------------- sprites: render with/without, shadow -> alpha
def sprite(draw, w_pt, h_pt, pad, floor):
    W_, H_ = int((w_pt + pad[0] + pad[1]) * S), int((h_pt + pad[2] + pad[3]) * S)
    shots = []
    for with_part in (True, False):
        c = R.Canvas(W_, H_, floor, R.MATTE, grain=0.0)
        c.hf[:] = LVL
        if with_part:
            draw(c, pad[0], pad[2])
        hf = c.hf.copy()
        shots.append((c.shade(ST), hf))
    (a, ha), (b, hb) = shots
    lum = lambda im: im[..., 0] * 0.3 + im[..., 1] * 0.59 + im[..., 2] * 0.11
    part = np.clip((ha - hb) / (0.5 * S), 0, 1)
    shade_ = np.clip(1 - lum(a) / np.maximum(lum(b), 1e-4), 0, 1)
    alpha = part + (1 - part) * shade_
    # feather to zero at the sprite border so a clipped shadow never shows as a box
    hh, ww = alpha.shape
    fy = np.minimum(np.arange(hh), np.arange(hh)[::-1])[:, None] / (10.0 * S)
    fx = np.minimum(np.arange(ww), np.arange(ww)[::-1])[None, :] / (10.0 * S)
    alpha = alpha * np.clip(np.minimum(fx, fy), 0, 1) ** 1.5 * (1 - part) + part
    rgb = a * part[..., None]
    out = np.dstack([np.where(alpha[..., None] > 1e-4, rgb / np.maximum(alpha[..., None], 1e-4), 0), alpha])
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- themes
# render: colours baked into the images; ui: colours the front end draws (LEDs, text, HUD, switches)
def _ui(led, led_rgb, ink, lab, title, dim, key_text, key_lit, key_led_off, tog_led_off, slot_on, dash_off, screen_bg, hud):
    return dict(led=led, ledRgb=led_rgb, ink=ink, lab=lab, title=title, dim=dim, keyText=key_text, keyLit=key_lit,
                keyLedOff=key_led_off, togLedOff=tog_led_off, slotOn=slot_on, dashOff=dash_off, screenBg=screen_bg,
                hud=dict(zip("gcmwa", ["rgb(%s)" % c for c in hud])))


THEMES = {
    "polar": dict(name="Polar", desc="white panel, blue LEDs, navy HUD",
                  render=dict(base="#E7E9EC", plate="#E2E5E9", knob="#F6F7F9", key="#2C2F35", screen="#061226", track="#CDD2D9"),
                  ui=_ui("#2696D6", "38,150,214", "#22262E", "#545A66", "#6A717E", "#AAB0B9", "#969BA4", "#F6F8FA", "#141619", "#CDD2D9",
                         "#2A2E36", "rgba(0,0,0,0.11)", "#061226", ["60,224,122", "56,214,240", "255,79,216", "226,232,238", "255,186,60"])),
    "graphite": dict(name="Graphite", desc="dark grey hardware, orange LEDs, amber HUD",
                     render=dict(base="#2E3034", plate="#28292D", knob="#45484E", key="#1A1B1E", screen="#08090B", track="#1A1B1E"),
                     knob_mat=(60, 0.3, 0),
                     ui=_ui("#FF7A2E", "255,122,46", "#E8EAED", "#A3A8B0", "#7E848D", "#5E636B", "#8D929A", "#FFFFFF", "#0B0C0E", "#5A5E66",
                            "#C9561C", "rgba(255,255,255,0.10)", "#08090B", ["255,160,70", "255,214,150", "255,255,255", "230,230,230", "255,96,64"])),
    "sand": dict(name="Sand", desc="warm Braun beige, charcoal keys, orange LEDs, amber HUD",
                 render=dict(base="#DDD6C8", plate="#D6CFC0", knob="#F4F0E8", key="#3A3733", screen="#19150F", track="#C3BBAA"),
                 ui=_ui("#F2631A", "242,99,26", "#2E2A25", "#6E665B", "#8A8174", "#B3AA9C", "#A9A196", "#FFF7EE", "#15130F", "#CFC7B8",
                        "#3A3733", "rgba(60,40,20,0.12)", "#19150F", ["255,176,72", "255,222,160", "255,107,26", "240,226,205", "255,90,60"])),
    "midnight": dict(name="Midnight", desc="navy panel, navy knobs, violet LEDs, cool HUD",
                     render=dict(base="#1D2236", plate="#191D2F", knob="#30375A", key="#11142A", screen="#060918", track="#12152A"),
                     knob_mat=(80, 0.35, 0),
                     ui=_ui("#9A88FF", "154,136,255", "#E6E8F5", "#9AA0C4", "#7B81A6", "#4C5277", "#8A90B5", "#FFFFFF", "#0A0C18", "#454B73",
                            "#6E5CE6", "rgba(255,255,255,0.09)", "#060918", ["120,150,255", "120,230,255", "255,120,220", "220,225,255", "255,190,90"])),
    "olive": dict(name="Olive", desc="field-equipment olive, cream knobs, amber LEDs, green phosphor",
                  render=dict(base="#4B503E", plate="#44493A", knob="#ECE6D2", key="#2A2D23", screen="#0A0D07", track="#33382B"),
                  ui=_ui("#FFB23F", "255,178,63", "#F1EEDC", "#B7BBA0", "#9A9E84", "#6E735C", "#A6AA90", "#FFF6DE", "#12140E", "#6A6F58",
                         "#C98A2A", "rgba(0,0,0,0.20)", "#0A0D07", ["120,255,120", "190,255,170", "255,210,90", "210,240,200", "255,178,63"])),
    "signal": dict(name="Signal", desc="light grey, orange keys, white knobs, mono HUD",
                   render=dict(base="#DADBDC", plate="#D3D4D6", knob="#FAFAFA", key="#F25A1E", screen="#101010", track="#BDBFC2"),
                   ui=_ui("#F25A1E", "242,90,30", "#141414", "#55585E", "#6D7076", "#A9ACB1", "#7A2A0A", "#FFFFFF", "#8A2C08", "#C9CBCE",
                          "#141414", "rgba(0,0,0,0.12)", "#101010", ["235,235,235", "255,255,255", "255,110,50", "200,200,200", "255,150,70"])),
    "ceramic": dict(name="Ceramic", desc="pale rose ceramic, white knobs, red LEDs, warm HUD",
                    render=dict(base="#E9DFDB", plate="#E3D8D3", knob="#FBF8F6", key="#3B3236", screen="#181013", track="#D3C6C3"),
                    knob_mat=(120, 0.45, 0),
                    ui=_ui("#E5483B", "229,72,59", "#2F2528", "#7A6A6E", "#8E7F82", "#BFB1B3", "#A99A9C", "#FFF4F2", "#160F11", "#D8CCCA",
                           "#3B3236", "rgba(60,20,20,0.10)", "#181013", ["255,150,128", "255,205,195", "255,72,59", "245,225,222", "255,190,90"])),
    "carbon": dict(name="Carbon", desc="all black, gloss black knobs, white LEDs, mono HUD",
                   render=dict(base="#161616", plate="#121212", knob="#232323", key="#0B0B0B", screen="#050505", track="#0C0C0C"),
                   knob_mat=(160, 0.6, 0),
                   ui=_ui("#F2F2F2", "242,242,242", "#EDEDED", "#8C8C8C", "#6E6E6E", "#454545", "#7A7A7A", "#FFFFFF", "#000000", "#3A3A3A",
                          "#EDEDED", "rgba(255,255,255,0.08)", "#050505", ["200,200,200", "255,255,255", "255,70,70", "175,175,175", "255,150,70"])),
}


def export_theme(tid, out):
    global ST
    th = THEMES[tid]
    ST = dict(R.STYLES["cockpit"])
    if th.get("knob_mat"):
        ST["knob"] = [tuple(list(k[:5]) + [th["knob_mat"]] + [k[6]]) for k in ST["knob"]]
    R.use_palette(ST)
    R.P.update(th["render"])
    B.DARK = th["render"]["key"]
    os.makedirs(out, exist_ok=True)
    for page in PAGES:
        background(page).save(os.path.join(out, "bg_%s.png" % page), optimize=True)
    knobs, keys, thumbs = all_sizes()
    meta = dict(knob={}, key={}, thumb={})
    for r in knobs:
        pad = (34, 34, 30, 52)
        im = sprite(lambda c, ox, oy, r=r: c.knob((ox + r) * S, (oy + r) * S, r * S, 0.0, ST, LVL), 2 * r, 2 * r, pad, R.P["plate"])
        im.save(os.path.join(out, "knob_%d.png" % r), optimize=True)
        meta["knob"][r] = dict(ox=pad[0] + r, oy=pad[2] + r)
    for (w, h) in keys:
        pad = (30, 30, 26, 46)
        floor = R.P["base"] if h == 22 else R.P["plate"]
        im = sprite(lambda c, ox, oy, w=w, h=h: B.ledslit(c, ox, oy, w, h, 0), w, h, pad, floor)
        im.save(os.path.join(out, "key_%dx%d.png" % (w, h)), optimize=True)
        meta["key"]["%dx%d" % (w, h)] = dict(ox=pad[0], oy=pad[2])
    for (w, h) in thumbs:
        tw, th_ = w * 0.76, h * 1.3
        pad = (26, 26, 24, 40)
        im = sprite(lambda c, ox, oy, tw=tw, th_=th_: c.rrect(ox * S, oy * S, tw * S, th_ * S, th_ / 2 * S, 3.2 * S, 0.3 * S, "round",
                                                                R.P["knob"], ST["knob"][0][5], LVL), tw, th_, pad, R.P["plate"])
        im.save(os.path.join(out, "thumb_%dx%d.png" % (w, h)), optimize=True)
        meta["thumb"]["%dx%d" % (w, h)] = dict(ox=pad[0], oy=pad[2], tw=tw, th=th_)
    return meta


def main():
    out = sys.argv[1]
    ids = sys.argv[2:] or list(THEMES)
    meta = None
    for tid in ids:
        meta = export_theme(tid, os.path.join(out, "themes", tid))
        print("theme", tid)
    spec = dict(top_keys=TOP_KEYS, screen=SCREEN, output=OUTPUT, extras=EXTRAS, pages=PAGES, sprites=meta,
                scene=[list(s) for s in R.SCENE])
    with open(os.path.join(out, "spec.js"), "w") as f:
        f.write("window.SPEC = " + json.dumps(spec) + ";\n")
    with open(os.path.join(out, "themes.js"), "w") as f:
        f.write("window.THEMES = " + json.dumps({k: dict(name=v["name"], desc=v["desc"], **v["ui"]) for k, v in THEMES.items()}) + ";\n")


if __name__ == "__main__":
    main()
