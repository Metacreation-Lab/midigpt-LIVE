#!/usr/bin/env python3
"""
Build patchers/MIDI-GPT Instrument.amxd: the per-track instrument tag.

A tiny MIDI effect that passes MIDI through untouched and holds one stored
parameter, "Instrument": a General MIDI program (1-128) or Drums. It is how a
Live track says what it is to MIDI-GPT -- saved with the set and carried by
the track through renames, reordering, duplication and copy/paste. The main
device finds it by name ("MIDI-GPT Instrument") through the Live API, reads
the parameter at generation time and writes it during Setup.

Usage: python3 tools/build_tag_device.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from maxtool import Doc, save, validate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT = lambda sub: os.path.join(ROOT, sub).replace(os.path.expanduser("~"), "~", 1)   # noqa: E731  where Max finds the files unfrozen
DST = os.path.join(ROOT, "patchers", "MIDI-GPT Instrument.amxd")

GM = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2",
    "Harpsichord", "Clavi", "Celesta", "Glockenspiel", "Music Box", "Vibraphone", "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Nylon Guitar", "Steel Guitar", "Jazz Guitar", "Clean Guitar", "Muted Guitar", "Overdriven Guitar", "Distortion Guitar",
    "Guitar Harmonics", "Acoustic Bass", "Finger Bass", "Pick Bass", "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1",
    "Synth Bass 2", "Violin", "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2", "Choir Aahs", "Voice Oohs", "Synth Voice",
    "Orchestra Hit", "Trumpet", "Trombone", "Tuba", "Muted Trumpet", "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax", "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
    "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina", "Square Lead", "Saw Lead", "Calliope Lead",
    "Chiff Lead", "Charang Lead", "Voice Lead", "Fifths Lead", "Bass + Lead", "New Age Pad", "Warm Pad", "Polysynth Pad", "Choir Pad",
    "Bowed Pad", "Metallic Pad", "Halo Pad", "Sweep Pad", "Rain", "Soundtrack", "Crystal", "Atmosphere", "Brightness", "Goblins",
    "Echoes", "Sci-fi", "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bagpipe", "Fiddle", "Shanai", "Tinkle Bell", "Agogo",
    "Steel Drums", "Woodblock", "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise", "Breath Noise",
    "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]
assert len(GM) == 128
ENUM = ["%d %s" % (i + 1, n) for i, n in enumerate(GM)] + ["Drums"]
WIDTH = 112
FAMILIES = ["PIANO", "CHROM PERC", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSEMBLE", "BRASS", "REED", "PIPE",
            "SYNTH LEAD", "SYNTH PAD", "SYNTH FX", "ETHNIC", "PERCUSSIVE", "SFX", "DRUMS"]
KEY_TEXT = [0.478, 0.478, 0.478, 1.0]   # the panel's key legend grey
CLEAR = [0.0, 0.0, 0.0, 0.0]
MENUS = [(8, 84, 96, 18), (8, 108, 96, 18)]   # tools/tag_device_assets.py MENUS: the key bodies


def box(**kw):
    return {"box": kw}


def face_menu(bid, name, enum, rect, xy):
    """A live.menu with no background over a key body: it draws its own legend and arrow (so its popup list is
    readable), to the right of the key's LED slit, which the face (midigpt_tag.js) draws."""
    x, y, w, h = rect
    return box(id=bid, maxclass="live.menu", varname=name.lower(), numinlets=1, numoutlets=3, outlettype=["", "", "float"],
               parameter_enable=1, presentation=1, presentation_rect=[x + 8, y + 1, w - 10, h - 2], patching_rect=[xy[0], xy[1], 100, 18],
               activebgcolor=CLEAR, bordercolor=CLEAR, focusbordercolor=CLEAR, textcolor=KEY_TEXT, tricolor=KEY_TEXT,
               fontname="Ableton Sans Bold", fontsize=7.5,
               saved_attribute_attributes={"valueof": {"parameter_enum": enum, "parameter_longname": name, "parameter_shortname": name,
                                                       "parameter_type": 2, "parameter_mmax": len(enum) - 1, "parameter_invisible": 2}})


def newobj(bid, text, xy, nin, nout, w=110):
    return box(id=bid, maxclass="newobj", text=text, numinlets=nin, numoutlets=nout, outlettype=[""] * nout,
               patching_rect=[xy[0], xy[1], w, 22])


def line(a, ao, b, bi):
    return {"patchline": {"source": [a, ao], "destination": [b, bi]}}


def build():
    boxes = [
        # front to back: the menus over the face
        face_menu("obj-family", "Family", FAMILIES, MENUS[0], (300, 200)),
        face_menu("obj-program", "Program", ["%d" % (i + 1) for i in range(8)], MENUS[1], (420, 200)),
        box(id="obj-face", maxclass="jsui", filename="midigpt_tag.js", numinlets=1, numoutlets=4, outlettype=["", "", "", ""],
            parameter_enable=0, border=0, presentation=1, presentation_rect=[0, 0, WIDTH, 169], patching_rect=[120, 300, 112, 169]),
        box(id="obj-in", maxclass="newobj", text="midiin", numinlets=1, numoutlets=1, outlettype=["int"], patching_rect=[30, 30, 46, 22]),
        box(id="obj-out", maxclass="newobj", text="midiout", numinlets=1, numoutlets=0, patching_rect=[30, 80, 52, 22]),
        # the stored value midigpt.js reads and writes ("Instrument"); not shown, the face shows it
        box(id="obj-menu", maxclass="live.menu", varname="instrument", numinlets=1, numoutlets=3, outlettype=["", "", "float"],
            parameter_enable=1, patching_rect=[120, 90, 140, 18],
            saved_attribute_attributes={"valueof": {
                "parameter_enum": ENUM, "parameter_longname": "Instrument", "parameter_shortname": "Instrument",
                "parameter_type": 2, "parameter_mmax": len(ENUM) - 1, "parameter_initial_enable": 1, "parameter_initial": [0],
                "parameter_invisible": 0}}),   # automatable: "Stored Only" parameters are not in the Live API, so midigpt.js could not find it
        newobj("obj-pre-inst", "prepend instrument", (120, 130), 1, 1),
        newobj("obj-pre-fam", "prepend family", (300, 240), 1, 1),
        newobj("obj-pre-prog", "prepend program", (420, 240), 1, 1),
        newobj("obj-thisdev", "live.thisdevice", (120, 40), 1, 3),
        newobj("obj-send", "s midigpt_tag_changed", (300, 420), 1, 0),
        newobj("obj-free", "freebang", (420, 380), 0, 1, w=70),
        box(id="obj-free-msg", maxclass="message", text="tag_changed", numinlets=2, numoutlets=1, outlettype=[""], patching_rect=[420, 410, 80, 22]),
    ]
    lines = [line("obj-in", 0, "obj-out", 0),
             line("obj-menu", 0, "obj-pre-inst", 0), line("obj-pre-inst", 0, "obj-face", 0),
             line("obj-thisdev", 0, "obj-menu", 0),                       # loaded: the menu reports its value to the face
             line("obj-family", 0, "obj-pre-fam", 0), line("obj-pre-fam", 0, "obj-face", 0),
             line("obj-program", 0, "obj-pre-prog", 0), line("obj-pre-prog", 0, "obj-face", 0),
             line("obj-face", 0, "obj-menu", 0), line("obj-face", 1, "obj-family", 0), line("obj-face", 2, "obj-program", 0),
             line("obj-face", 3, "obj-send", 0),
             line("obj-free", 0, "obj-free-msg", 0), line("obj-free-msg", 0, "obj-send", 0)]   # removed: tell the main device too
    patcher = {
        "fileversion": 1,
        "appversion": {"major": 8, "minor": 6, "revision": 5, "architecture": "x64", "modernui": 1},
        "classnamespace": "box", "rect": [100.0, 100.0, 520.0, 300.0], "openrect": [0.0, 0.0, 0.0, 169.0],
        "bglocked": 0, "openinpresentation": 1, "default_fontsize": 10.0, "default_fontface": 0,
        "default_fontname": "Arial Bold", "gridonopen": 1, "gridsize": [8.0, 8.0], "gridsnaponopen": 1,
        "objectsnaponopen": 0, "statusbarvisible": 2, "toolbarvisible": 1, "boxanimatetime": 500,
        "enablehscroll": 1, "enablevscroll": 1, "devicewidth": float(WIDTH),
        "description": "MIDI-GPT: which General MIDI instrument this track is", "digest": "", "tags": "",
        "style": "", "subpatcher_template": "", "assistshowspatchername": 0,
        "boxes": boxes, "lines": lines,
        "parameters": {"obj-menu": ["Instrument", "Instrument", 0], "obj-family": ["Family", "Family", 0], "obj-program": ["Program", "Program", 0], "parameterbanks": {"0": {"index": 0, "name": "", "parameters": ["-"] * 8}},
                       "inherited_shortname": 1},
        "dependency_cache": [{"name": "midigpt_tag.js", "bootpath": BOOT("javascript"), "type": "TEXT", "implicit": 1},
                             {"name": "midigpt_tag_bg.png", "bootpath": BOOT("media/panel"), "type": "PNG", "implicit": 1}], "latency": 0, "is_mpe": 0, "minimum_live_version": "", "minimum_max_version": "",
        "project": {"version": 1, "creationdate": 3590052493, "modificationdate": 3590052493, "viewrect": [0.0, 0.0, 300.0, 500.0],
                    "autoorganize": 1, "hideprojectwindow": 1, "showdependencies": 1, "autolocalize": 0,
                    "contents": {"patchers": {}}, "layout": {}, "searchpath": {}, "detailsvisible": 0,
                    "amxdtype": int.from_bytes(b"mmmm", "big"), "readonly": 0, "devpathtype": 0, "devpath": ".",
                    "sortmode": 0, "viewmode": 0, "includepackages": 0},
    }
    header = b"ampf" + (4).to_bytes(4, "little") + b"mmmm" + b"meta" + (4).to_bytes(4, "little") + (1).to_bytes(4, "little") + b"ptch" + b"\0\0\0\0"
    return Doc(DST, {"patcher": patcher}, header, b"")


if __name__ == "__main__":
    doc = build()
    errors, _ = validate(doc)
    if errors:
        sys.exit("refusing to save:\n  " + "\n  ".join(errors))
    save(doc)
    print("saved", os.path.relpath(DST, ROOT))
