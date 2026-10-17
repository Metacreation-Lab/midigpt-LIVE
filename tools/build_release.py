#!/usr/bin/env python3
"""
Build the release zip: both devices frozen (scripts and images embedded), in one
folder that is copied into Live's User Library as is.

  dist/MIDI-GPT/MIDI-GPT.amxd
  dist/MIDI-GPT/MIDI-GPT Instrument.amxd      the track tag; MIDI-GPT opens it by file
  dist/MIDI-GPT/README.txt
  dist/MIDI-GPT-for-Live-<version>.zip         what install.sh downloads (a GitHub release asset)

The scripts are frozen with their include()d and require()d files inlined:
Max does not reliably embed files that are only pulled in by include().

  python3 tools/build_release.py            (version from VERSION)
"""

import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amxd_freeze as F  # noqa: E402
import maxtool as M  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, "javascript")
MEDIA = os.path.join(ROOT, "media", "panel")
DIST = os.path.join(ROOT, "dist")
FOLDER = "MIDI-GPT"
DEVICES = ["MIDI-GPT.amxd", "MIDI-GPT Instrument.amxd"]
NODE_SCRIPTS = {"midigpt_node.js"}      # run by Node, which has its own require()

INCLUDE = re.compile(r"""^[ \t]*include\(\s*["']([^"']+)["']\s*\)\s*;?[ \t]*$""", re.M)
REQUIRE = re.compile(r"""\brequire\(\s*["']([^"']+)["']\s*\)""")

README = """MIDI-GPT for Ableton Live {version}

Install
  Copy this MIDI-GPT folder into your Live User Library, for example
    ~/Music/Ableton/User Library/
  (or run the installer, which does this for you). Keep both devices in the
  same folder: MIDI-GPT adds "MIDI-GPT Instrument" to your tracks by itself.

Use
  1. Start the MIDI-GPT server ("Start MIDI-GPT Server" from the installer,
     or: midigpt-http --pretrained yellow_medium --port 3456).
  2. Drag MIDI-GPT onto a track and open its window.
  3. The server address is in SETUP (default http://127.0.0.1:3456).

Needs Live 11 or 12 with Max for Live (Suite, or Standard + Max for Live).
https://github.com/{repo}
"""


def script_path(name):
    name = name if name.endswith(".js") else name + ".js"
    path = os.path.join(JS, name)
    if not os.path.isfile(path):
        sys.exit("build_release: script not found: " + name)
    return path


def inline(name, seen=()):
    """The script with every include() pasted in place and every require() as a module wrapper."""
    src = open(script_path(name), encoding="utf-8").read()
    if name in NODE_SCRIPTS:
        return src

    def inc(m):
        if m.group(1) in seen:
            sys.exit("build_release: include loop at " + m.group(1))
        return "// ---- include(%s), inlined by build_release.py\n%s\n// ---- end %s" % (
            m.group(1), inline(m.group(1), seen + (name,)), m.group(1))

    def req(m):
        body = inline(m.group(1), seen + (name,))
        return "(function () { var exports = {}, module = { exports: exports };\n%s\nreturn module.exports; })()" % body

    return REQUIRE.sub(req, INCLUDE.sub(inc, src))


def main():
    version = open(os.path.join(ROOT, "VERSION")).read().strip()
    repo = os.environ.get("MIDIGPT_LIVE_REPO", "DaoTwenty/midigpt-LIVE")
    stage = os.path.join(DIST, "stage")
    out = os.path.join(DIST, FOLDER)
    for d in (stage, out):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    for dev in DEVICES:
        src = os.path.join(ROOT, "patchers", dev)
        p = M.load(src).patcher
        scripts = sorted({F.with_ext(n) for n in F.box_refs(p) if F.with_ext(n).endswith(".js")})
        for s in scripts:
            with open(os.path.join(stage, s), "w", encoding="utf-8") as f:
                f.write(inline(s))
        # images: the ones named in the patch and in Image("...") literals, plus every panel sprite
        # (midigpt_panel.js builds those names at runtime, so nothing can follow them)
        extra = [f for f in os.listdir(MEDIA) if f.startswith("midigpt_") and f != "midigpt_tag_bg.png"] if dev == "MIDI-GPT.amxd" else []
        files, missing = F.collect(p, [stage, MEDIA], extra, use_cache=False)
        if missing:
            sys.exit("build_release: %s needs files that were not found: %s" % (dev, ", ".join(missing)))
        F.freeze(src, os.path.join(out, dev), [], files=files)
        size = os.path.getsize(os.path.join(out, dev))
        print("froze %-26s %3d files  %6.1f KB" % (dev, len(files), size / 1024))

    with open(os.path.join(out, "README.txt"), "w") as f:
        f.write(README.format(version=version, repo=repo))
    shutil.rmtree(stage)

    zpath = os.path.join(DIST, "MIDI-GPT-for-Live-%s.zip" % version)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(out)):
            z.write(os.path.join(out, name), FOLDER + "/" + name)
    print("wrote", os.path.relpath(zpath, ROOT), "(%.1f KB)" % (os.path.getsize(zpath) / 1024))


if __name__ == "__main__":
    main()
