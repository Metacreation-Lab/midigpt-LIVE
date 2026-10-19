#!/usr/bin/env python3
"""
(Re)build patchers/MIDI-GPT.amxd in place: its floating window ("p main_window")
becomes the panel, region jsuis (javascript/midigpt_panel.js) drawn over the
rendered lo-fi assets in media/panel/ (tools/export_panel_assets.py); the strip
in Live's device chain becomes one key that opens it; the dependency list is
rewritten from what the device uses. Safe to re-run.

midigpt.js outlets: 0 -> the window (panel_state <json> / panel_notes <json>),
1 -> the dev bridge's udpsend, 2 -> the node.script helper. The panel's
"panel ..." messages go straight back to midigpt.js; "url_edit" / "url_text"
show the native address field (a textedit, varname setup_url) over the Setup
screen, and Enter in it sends server_url. "seed_edit" opens the seed field
(seed_text) over the seed readout; Enter in it sends "panel seed_text <text>".

Usage: python3 tools/build_device.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from maxtool import load, save, validate, find_box  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "patchers", "MIDI-GPT.amxd")   # the name Live shows on the device
BG = [0.086, 0.086, 0.086, 1.0]
HOME = os.path.expanduser("~")
# where Max looks for an unfrozen device's files: this checkout (a frozen release embeds them instead)
BOOT = lambda sub: os.path.join(ROOT, sub).replace(HOME, "~", 1)   # noqa: E731
JS_BOOTPATH = BOOT("javascript")
MEDIA_BOOTPATH = BOOT("media/panel")
SCRIPTS = ("midigpt.js", "midigpt_panel_link.js", "midigpt_node.js", "midigpt_panel.js", "midigpt_canvas.js",
           "midigpt_panel_spec.js", "midigpt_strip.js")
JS_OUTLETS = {6: 0, 8: 1, 9: 2}   # the old 10-outlet layout -> panel, bridge, node
# the old window and its open/close controls (removed on the first run)
LEGACY_TOP = ("obj-32", "obj-25", "obj-27", "obj-20", "obj-23", "obj-7", "obj-17", "obj-19")
WINDOW_INLETS = ("obj-2", "obj-4")   # 0: pcontrol (open), 1: panel state
URL_RECT = [54, 298, 284, 16]
SEED_RECT = [602, 403, 72, 11]      # the seed readout on the main page (midigpt_panel.js seedRect: 598, 395, 76 x 20)
REGIONS = [("top", [788, 2, 168, 34]), ("roll", [4, 36, 952, 220]), ("main", [4, 256, 684, 264]),   # midigpt_panel.js REGIONS
           ("output", [688, 256, 268, 264]), ("masks", [4, 520, 952, 118])]   # the Setup page's server screen (32, 292, 320, 28), inside its readout


def newobj(box_id, text, xy, nin, nout, w=120):
    return {"box": {"id": box_id, "maxclass": "newobj", "text": text, "numinlets": nin, "numoutlets": nout,
                    "outlettype": [""] * nout, "patching_rect": [xy[0], xy[1], w, 22]}}


def msg(box_id, text, xy, w=60):
    return {"box": {"id": box_id, "maxclass": "message", "text": text, "numinlets": 2, "numoutlets": 1,
                    "outlettype": [""], "patching_rect": [xy[0], xy[1], w, 22]}}


def line(src, so, dst, di):
    return {"patchline": {"source": [src, so], "destination": [dst, di]}}


def build_window(old):
    keep = [b for b in old["boxes"] if b["box"]["maxclass"] == "outlet" or b["box"]["id"] in WINDOW_INLETS]
    boxes, lines = [], []
    # front to back (file order is z-order): the address field over the panel
    boxes.append({"box": {"id": "obj-p-url", "maxclass": "textedit", "varname": "setup_url", "keymode": 1, "outputmode": 1,
                          "numinlets": 1, "numoutlets": 4, "outlettype": ["", "int", "", ""], "parameter_enable": 0,
                          "hidden": 1, "presentation": 1, "presentation_rect": URL_RECT,
                          "patching_rect": [40, 520, 284, 16], "text": "",
                          "fontname": "Ableton Sans Bold", "fontsize": 7.5,
                          "textcolor": [0.784, 0.784, 0.784, 1.0], "bgcolor": [0.02, 0.02, 0.02, 1.0],
                          "bordercolor": [0.02, 0.02, 0.02, 1.0], "border": 0}})
    boxes.append({"box": {"id": "obj-p-seed", "maxclass": "textedit", "varname": "seed_text", "keymode": 1, "outputmode": 1,
                          "numinlets": 1, "numoutlets": 4, "outlettype": ["", "int", "", ""], "parameter_enable": 0,
                          "hidden": 1, "presentation": 1, "presentation_rect": SEED_RECT,
                          "patching_rect": [40, 700, 120, 16], "text": "", "textjustification": 1,
                          "fontname": "Ableton Sans Bold", "fontsize": 7.2,
                          "textcolor": [1.0, 1.0, 1.0, 1.0], "bgcolor": [0.0, 0.0, 0.0, 0.0],      # see-through: the panel draws the frame and hint
                          "bordercolor": [0.0, 0.0, 0.0, 0.0], "border": 0}})
    ids = []
    for i, (region, rect) in enumerate(REGIONS):
        bid = "obj-p-" + region
        ids.append(bid)
        boxes.append({"box": {"id": bid, "maxclass": "jsui", "filename": "midigpt_panel.js", "jsarguments": [region], "varname": "panel_" + region,
                              "numinlets": 1, "numoutlets": 1, "outlettype": [""], "parameter_enable": 0, "border": 0,
                              "presentation": 1, "presentation_rect": rect, "patching_rect": [40 + i * 130, 300, 120, 90]}})
    # the page background: one native picture, switched by name when the panel changes page ("bg <page>"); three
    # loaded at once held ~30 MB of decoded pixels per device, and a picture per layout couldn't show ENGINE's second
    boxes.append({"box": {"id": "obj-p-bgpic", "maxclass": "fpic", "pic": "midigpt_bg_main.png", "autofit": 1, "numinlets": 1,
                          "numoutlets": 1, "varname": "bg_page", "outlettype": ["jit_matrix"], "presentation": 1,
                          "presentation_rect": [0, 0, 960, 640], "patching_rect": [700, 300, 96, 64], "ignoreclick": 1}})

    # midigpt.js outlet 6 -> every region
    boxes.append(newobj("obj-p-route", "route panel_state panel_notes", (40, 120), 1, 3, w=200))
    boxes += [newobj("obj-p-pre-s", "prepend panel_state", (40, 160), 1, 1), newobj("obj-p-pre-n", "prepend panel_notes", (180, 160), 1, 1)]
    lines += [line("obj-4", 0, "obj-p-route", 0), line("obj-p-route", 0, "obj-p-pre-s", 0), line("obj-p-route", 1, "obj-p-pre-n", 0)]
    for bid in ids:
        lines.append(line("obj-p-pre-s", 0, bid, 0))
    lines.append(line("obj-p-pre-n", 0, "obj-p-roll", 0))     # only the roll draws notes

    # regions -> midigpt.js, except the address field, the page switch and the background picture
    boxes.append(newobj("obj-p-out", "route url_edit url_text page bg seed_edit seed_set", (40, 480), 1, 7, w=300))
    boxes.append(newobj("obj-p-page", "prepend page", (260, 440), 1, 1, w=90))
    # "bg <page>" from the panel -> pic midigpt_bg_<page>.png into the background picture
    boxes += [newobj("obj-p-bgname", "sprintf symout midigpt_bg_%s.png", (360, 400), 1, 1, w=200),
              newobj("obj-p-bgpre", "prepend pic", (360, 430), 1, 1, w=80)]
    lines += [line("obj-p-out", 3, "obj-p-bgname", 0), line("obj-p-bgname", 0, "obj-p-bgpre", 0), line("obj-p-bgpre", 0, "obj-p-bgpic", 0)]
    for bid in ids:
        lines += [line(bid, 0, "obj-p-out", 0), line("obj-p-page", 0, bid, 0)]
    lines.append(line("obj-p-out", 2, "obj-p-page", 0))
    lines.append(line("obj-p-out", 2, "obj-p-hide", 0))
    lines.append(line("obj-p-sel", 0, "obj-p-url-done", 0))   # closed from any region: the Setup screen shows the address again
    boxes += [newobj("obj-p-sel", "sel 0 1", (40, 560), 1, 3, w=60),
              msg("obj-p-hide", "script hide setup_url", (40, 600), 140),
              msg("obj-p-show", "script show setup_url, script sendbox setup_url select", (190, 600), 300),
              newobj("obj-p-settext", "prepend set", (200, 520), 1, 1, w=80),
              newobj("obj-p-thispatcher", "thispatcher", (40, 650), 1, 2, w=80)]
    lines += [line("obj-p-out", 0, "obj-p-sel", 0), line("obj-p-sel", 0, "obj-p-hide", 0), line("obj-p-sel", 1, "obj-p-show", 0),
              line("obj-p-hide", 0, "obj-p-thispatcher", 0), line("obj-p-show", 0, "obj-p-thispatcher", 0),
              line("obj-p-out", 1, "obj-p-settext", 0), line("obj-p-settext", 0, "obj-p-url", 0),
              line("obj-p-out", 6, "obj-1", 0)]

    # Enter in the address field: server_url to midigpt.js, then hide the field and tell the panel
    boxes += [newobj("obj-p-url-route", "route text", (340, 520), 1, 2, w=70),
              newobj("obj-p-url-t", "t b l", (340, 550), 1, 2, w=50),
              newobj("obj-p-url-prep", "prepend server_url", (400, 580), 1, 1, w=120),
              msg("obj-p-url-done", "url_done", (340, 580), 60)]
    lines += [line("obj-p-url", 0, "obj-p-url-route", 0), line("obj-p-url-route", 0, "obj-p-url-t", 0), line("obj-p-url-route", 1, "obj-p-url-t", 0),
              line("obj-p-url-t", 1, "obj-p-url-prep", 0), line("obj-p-url-prep", 0, "obj-1", 0),
              line("obj-p-url-t", 0, "obj-p-url-done", 0), line("obj-p-url-done", 0, "obj-p-main", 0),
              line("obj-p-url-t", 0, "obj-p-hide", 0)]

    # the seed readout: "seed_edit 1" (a click on it) opens an empty field, Enter sends "panel seed_text <text>"
    # (empty = random) to midigpt.js, closes the field and tells the panel; a page switch closes it too
    boxes += [newobj("obj-p-seed-sel", "sel 0 1", (40, 740), 1, 3, w=60),
              msg("obj-p-seed-hide", "script hide seed_text", (40, 780), 140),
              msg("obj-p-seed-show", "script sendbox seed_text set, script show seed_text, script sendbox seed_text select", (190, 780), 420),
              newobj("obj-p-seed-route", "route text", (340, 700), 1, 2, w=70),
              newobj("obj-p-seed-t", "t b l", (340, 730), 1, 2, w=50),
              newobj("obj-p-seed-prep", "prepend panel seed_text", (400, 760), 1, 1, w=150),
              msg("obj-p-seed-done", "seed_done 1", (340, 760), 80)]
    lines += [line("obj-p-out", 4, "obj-p-seed-sel", 0), line("obj-p-seed-sel", 0, "obj-p-seed-hide", 0), line("obj-p-seed-sel", 1, "obj-p-seed-show", 0),
              line("obj-p-seed-hide", 0, "obj-p-thispatcher", 0), line("obj-p-seed-show", 0, "obj-p-thispatcher", 0),
              line("obj-p-out", 2, "obj-p-seed-hide", 0),
              line("obj-p-seed", 0, "obj-p-seed-route", 0), line("obj-p-seed-route", 0, "obj-p-seed-t", 0), line("obj-p-seed-route", 1, "obj-p-seed-t", 0),
              line("obj-p-seed-t", 1, "obj-p-seed-prep", 0), line("obj-p-seed-prep", 0, "obj-1", 0),
              line("obj-p-seed-t", 0, "obj-p-seed-done", 0), line("obj-p-seed-done", 0, "obj-p-main", 0),
              line("obj-p-seed-t", 0, "obj-p-seed-hide", 0)]
    # digits only: every key typed goes to the panel (seed_key), which sends back the clean entry (seed_set), set
    # into the field after the key has landed (deferlow)
    boxes += [newobj("obj-p-seed-key", "prepend seed_key", (180, 700), 1, 1, w=110),
              newobj("obj-p-seed-defer", "deferlow", (40, 820), 1, 1, w=60),
              newobj("obj-p-seed-set", "prepend set", (110, 820), 1, 1, w=80)]
    lines += [line("obj-p-seed", 1, "obj-p-seed-key", 0), line("obj-p-seed-key", 0, "obj-p-main", 0),
              line("obj-p-out", 5, "obj-p-seed-defer", 0), line("obj-p-seed-defer", 0, "obj-p-seed-set", 0),
              line("obj-p-seed-set", 0, "obj-p-seed", 0)]

    # size the window. The panel says "ready" itself on its first paint (the window is open): the state pushes
    # start then, not at device load.
    boxes += [newobj("obj-p-lb", "loadbang", (700, 40), 1, 1, w=60),
              newobj("obj-p-defer", "deferlow", (700, 70), 1, 1, w=60),
              msg("obj-p-winmsg", "title MIDI-GPT, window size 200 80 1160 720, window flags nogrow, window flags nozoom, window exec, "
                                  "presentation 1, scrollto 0 0", (800, 100), 420),
              newobj("obj-p-thispatcher2", "thispatcher", (800, 140), 1, 2, w=80)]
    lines += [line("obj-p-lb", 0, "obj-p-defer", 0),
              line("obj-p-defer", 0, "obj-p-winmsg", 0), line("obj-p-winmsg", 0, "obj-p-thispatcher2", 0)]

    boxes.append({"box": {"id": "obj-p-bg", "maxclass": "panel", "mode": 0, "bgcolor": BG, "rounded": 0,
                          "numinlets": 1, "numoutlets": 0, "background": 1,
                          "presentation": 1, "presentation_rect": [0, 0, 960, 640], "patching_rect": [700, 200, 80, 50]}})
    boxes += keep
    return boxes, lines


STRIP_W = 96


def build_strip(top):
    """The device in Live's chain: one key with the MIDI-GPT mark; pressing it opens the window."""
    boxes, lines = top["boxes"], top["lines"]
    old = {b["box"]["id"]: b for b in boxes}
    if "obj-strip" in old:
        old["obj-strip"]["box"]["filename"] = "midigpt_strip.js"
        return
    x0, y0 = 900, 40
    pc = next(b["box"]["id"] for b in boxes if b["box"].get("text", "") == "pcontrol")
    boxes.append({"box": dict(id="obj-strip", maxclass="jsui", filename="midigpt_strip.js", numinlets=1, numoutlets=1, outlettype=[""], parameter_enable=0, border=0,
                              presentation=1, presentation_rect=[0, 0, STRIP_W, 169], patching_rect=[x0, y0 + 120, 96, 169])})
    def newobj(bid, text, xy, nin, nout, w=120):
        return {"box": {"id": bid, "maxclass": "newobj", "text": text, "numinlets": nin, "numoutlets": nout, "outlettype": [""] * nout,
                        "patching_rect": [xy[0], xy[1], w, 22]}}
    # a click on the key: flash the mark, open the window (open again just brings it to the front)
    boxes += [newobj("obj-strip-opensel", "t b b", (x0, y0 + 40), 1, 2, w=40),
              {"box": {"id": "obj-strip-press", "maxclass": "message", "text": "flash", "numinlets": 2, "numoutlets": 1,
                       "outlettype": [""], "patching_rect": [x0 + 60, y0 + 70, 40, 22]}},
              {"box": {"id": "obj-strip-openmsg", "maxclass": "message", "text": "open", "numinlets": 2, "numoutlets": 1,
                       "outlettype": [""], "patching_rect": [x0, y0 + 70, 40, 22]}}]
    lines += [{"patchline": {"source": ["obj-strip", 0], "destination": ["obj-strip-opensel", 0]}},
              {"patchline": {"source": ["obj-strip-opensel", 1], "destination": ["obj-strip-press", 0]}},
              {"patchline": {"source": ["obj-strip-press", 0], "destination": ["obj-strip", 0]}},
              {"patchline": {"source": ["obj-strip-opensel", 0], "destination": ["obj-strip-openmsg", 0]}},
              {"patchline": {"source": ["obj-strip-openmsg", 0], "destination": [pc, 0]}}]
    top["devicewidth"] = float(STRIP_W)
    top["openrect"] = [0.0, 0.0, float(STRIP_W), 169.0]


def drop(top, ids):
    """Remove boxes and every patch cord touching them."""
    top["boxes"] = [b for b in top["boxes"] if b["box"]["id"] not in ids]
    top["lines"] = [l for l in top["lines"] if l["patchline"]["source"][0] not in ids and l["patchline"]["destination"][0] not in ids]


def main():
    doc = load(DST)
    top = doc.patcher
    drop(top, set(LEGACY_TOP))

    mw = find_box(top, "obj-13")
    p = mw["patcher"]
    p["boxes"], p["lines"] = build_window(p)
    p["rect"] = [200.0, 80.0, 960.0, 640.0]
    p["toolbarvisible"] = 0
    p["statusbarvisible"] = 0
    p["openinpresentation"] = 1
    for k in ("bgcolor", "editing_bgcolor"):
        p[k] = BG
    mw["numinlets"] = len(WINDOW_INLETS)

    params = top["parameters"]
    for table in (params, params.get("parameter_overrides", {})):
        for key in list(table):
            if key.startswith("obj-13::"):
                del table[key]

    # the core script: 3 outlets (panel, bridge, node); the window's panel inlet is now its 2nd
    js = next(b["box"] for b in top["boxes"] if b["box"].get("text", "").startswith("js "))
    js["text"] = "js midigpt.js 0"
    js.setdefault("saved_object_attributes", {})["filename"] = "midigpt.js"
    if js.get("numoutlets") == 10:
        cords = []
        for l in top["lines"]:
            src, dst = l["patchline"]["source"], l["patchline"]["destination"]
            if src[0] == js["id"]:
                if src[1] not in JS_OUTLETS:
                    continue
                src[1] = JS_OUTLETS[src[1]]
                if dst[0] == "obj-13":
                    dst[1] = 1
            cords.append(l)
        top["lines"] = cords
    js["numoutlets"] = 3
    js["outlettype"] = [""] * 3
    for b in top["boxes"]:
        bb = b["box"]
        if bb.get("text", "").startswith("node.script"):
            bb["text"] = "node.script midigpt_node.js @autostart 1"
        elif bb.get("text", "").startswith("r ") and "tag_changed" in bb["text"]:
            bb["text"] = "r midigpt_tag_changed"
        elif bb["id"] == "obj-bridge-comment":
            bb["text"] = "dev bridge (tools/bridge.py) -- inert unless .midigpt_dev exists"

    build_strip(top)

    # a MIDI-GPT Instrument tag was added, changed or removed anywhere in the set: re-read the tracks
    if not any(b["box"]["id"] == "obj-tagrecv" for b in top["boxes"]):
        x, y = js["patching_rect"][0], js["patching_rect"][1]
        top["boxes"].append({"box": {"id": "obj-tagrecv", "maxclass": "newobj", "text": "r midigpt_tag_changed", "numinlets": 0, "numoutlets": 1,
                                     "outlettype": [""], "patching_rect": [x + 260, y - 40, 120, 22]}})
        top["lines"].append({"patchline": {"source": ["obj-tagrecv", 0], "destination": [js["id"], 0]}})

    # what Max needs to find the files (in this checkout) while the device is unfrozen
    media = os.path.join(ROOT, "media", "panel")
    deps = [{"name": f, "bootpath": JS_BOOTPATH, "type": "TEXT", "implicit": 1} for f in SCRIPTS]
    deps += [{"name": f, "bootpath": MEDIA_BOOTPATH, "type": "PNG", "implicit": 1}
             for f in sorted(os.listdir(media)) if f.startswith("midigpt_") and f != "midigpt_tag_bg.png"]
    top["dependency_cache"] = deps

    errors, _ = validate(doc)
    if errors:
        sys.exit("refusing to save:\n  " + "\n  ".join(errors))
    save(doc)
    print("saved", os.path.relpath(DST, ROOT))


if __name__ == "__main__":
    main()
