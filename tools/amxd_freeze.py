#!/usr/bin/env python3
"""
Freeze a Max for Live device without opening Max: embed the files it uses
(scripts, images, abstractions) in the .amxd, the way Max's "Freeze Device"
does, so the device works as a single downloaded file.

A frozen .amxd is the usual header (ampf <type>, meta, ptch <length>) followed
by an "mx@c" container:

  mx@c  <u32 16> <u32 0> <u32 offset of dlst>     (big endian, from "mx@c")
  <the device's own patcher JSON>                  first entry, flag 17
  <each embedded file, back to back>
  dlst  <u32 size>
    dire <u32 size>  type <4cc>  fnam <name, NUL padded to 4>  sz32  of32
                     vers  flag  mdat (Mac seconds since 1904)  -- one per file

  python3 tools/amxd_freeze.py check <device.amxd>...          list a frozen device's files
  python3 tools/amxd_freeze.py roundtrip <device.amxd>...      re-pack frozen devices, compare bytes
  python3 tools/amxd_freeze.py freeze <in.amxd> <out.amxd> <search dir>...
"""

import json
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maxtool as M  # noqa: E402

MAC_EPOCH = 2082844800   # 1904-01-01 -> 1970-01-01
TYPES = {".js": b"TEXT", ".json": b"TEXT", ".txt": b"TEXT", ".maxpat": b"JSON", ".amxd": b"JSON",
         ".png": b"PNG ", ".jpg": b"JPEG", ".svg": b"svg "}


def _chunk(tag, body):
    return tag + struct.pack(">I", len(body) + 8) + body


def _sub(data):
    out, k = {}, 0
    while k < len(data):
        tag, size = struct.unpack(">4sI", data[k:k + 8])
        out[tag.decode("latin1")] = data[k + 8:k + size]
        k += size
    return out


def read(path):
    """-> (header bytes up to 'ptch', [entry dicts]) for a frozen device."""
    raw = open(path, "rb").read()
    p = raw.find(b"mx@c")
    if p < 0 or raw[p - 8:p - 4] != b"ptch":
        raise ValueError(path + ": not a frozen device")
    head = raw[:p - 8]
    _, _, _, doff = struct.unpack(">4sIII", raw[p:p + 16])
    box = raw[p:]
    dsize = struct.unpack(">I", box[doff + 4:doff + 8])[0]
    entries, j = [], doff + 8
    while j < doff + dsize:
        size = struct.unpack(">I", box[j + 4:j + 8])[0]
        f = _sub(box[j + 8:j + size])
        u = lambda k: struct.unpack(">I", f[k])[0]   # noqa: E731
        entries.append(dict(type=f["type"], name=f["fnam"].rstrip(b"\0").decode("utf-8"),
                            data=box[u("of32"):u("of32") + u("sz32")],
                            vers=u("vers"), flag=u("flag"), mdat=u("mdat"), _order=list(f)))
        j += size
    return head, entries


def pack(head, entries):
    """Inverse of read(): header + mx@c container with the entries in order."""
    body, dlst, off = b"", b"", 16
    for e in entries:
        body += e["data"]
        name = e["name"].encode("utf-8") + b"\0"
        name += b"\0" * (-len(name) % 4)
        fields = dict(type=e["type"], fnam=name, sz32=struct.pack(">I", len(e["data"])), of32=struct.pack(">I", off),
                      vers=struct.pack(">I", e.get("vers", 0)), flag=struct.pack(">I", e.get("flag", 0)),
                      mdat=struct.pack(">I", e.get("mdat", 0)))
        order = e.get("_order") or ["type", "fnam", "sz32", "of32", "vers", "flag", "mdat"]
        dlst += _chunk(b"dire", b"".join(_chunk(k.encode(), fields[k]) for k in order))
        off += len(e["data"])
    box = b"mx@c" + struct.pack(">III", 16, 0, off) + body + _chunk(b"dlst", dlst)
    return head + b"ptch" + struct.pack("<I", len(box)) + box


# ------------------------------------------------------------------ dependencies
# include("x") / require("x") / new Image("x.png") with a literal name, outside // comments
JS_REFS = re.compile(r"""^(?![ \t]*//).*?(?:\b(?:include|require)\s*\(\s*["']([^"']+)["']\s*\)|\bnew\s+Image\s*\(\s*["']([^"']+)["']\s*\))""", re.M)


def box_refs(patcher):
    """File names a patcher refers to: js/jsui/node.script scripts, fpic images, abstractions."""
    out = []
    for _, bb in M.boxes(patcher):
        cls, text = bb.get("maxclass"), bb.get("text", "")
        words = text.split()
        if cls == "jsui" and bb.get("filename"):
            out.append(bb["filename"])
        elif cls == "newobj" and words and words[0] in ("js", "node.script") and len(words) > 1:
            out.append(words[1])
        elif cls == "fpic" and bb.get("pic"):
            out.append(bb["pic"])
        elif cls == "bpatcher" and bb.get("name"):
            out.append(bb["name"])
    return out


def with_ext(name):
    return name if os.path.splitext(name)[1] else name + ".js"


def find(name, dirs):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def collect(patcher, dirs, extra=(), use_cache=True):
    """Every file the device needs, following include()/require()/Image() inside scripts. -> {name: path}
    use_cache also takes the names in the device's dependency_cache (what Max last saw it use)."""
    want = [with_ext(n) for n in box_refs(patcher)] + list(extra)
    if use_cache:
        want += [d["name"] for d in patcher.get("dependency_cache", [])]
    found, missing = {}, []
    while want:
        name = os.path.basename(want.pop(0))
        if name in found or name in missing:
            continue
        path = find(name, dirs)
        if not path:
            missing.append(name)
            continue
        found[name] = path
        if name.endswith(".js"):
            for m in JS_REFS.finditer(open(path, encoding="utf-8", errors="replace").read()):
                ref = m.group(1) or m.group(2)
                if ref != "max-api" and not ref.startswith(("child_process", "fs", "os", "path")):
                    want.append(with_ext(ref) if m.group(1) else ref)
            # js/jsui Image() names built at runtime ("midigpt_" + name + ".png") cannot be followed:
            # the caller passes those (all of a media folder) in `extra`
        elif name.endswith(".maxpat"):
            want += [with_ext(n) for n in box_refs(json.load(open(path))["patcher"])]
    return found, missing


def mac_time(path):
    return int(os.path.getmtime(path)) + MAC_EPOCH


def freeze(src, out, dirs, extra=(), files=None):
    """Write `out`: `src` frozen with everything it needs from `dirs` (or exactly `files`, {name: path})."""
    doc = M.load(src)
    p = doc.patcher
    if files is None:
        files, missing = collect(p, dirs, extra)
        if missing:
            raise SystemExit("freeze: not found: " + ", ".join(missing))
    deps = []
    for name in sorted(files):
        ext = os.path.splitext(name)[1].lower()
        deps.append({"name": name, "bootpath": "~/Documents/Max 8/Max for Live Devices/MIDI-GPT Project",
                     "type": {".js": "TEXT", ".png": "PNG", ".maxpat": "JSON", ".svg": "svg"}.get(ext, "TEXT"),
                     "implicit": 1})
    p["dependency_cache"] = deps
    p.setdefault("project", {})["readonly"] = 1
    main = M.dumps(doc.data).encode("utf-8") + b"\n\0"
    entries = [dict(type=b"JSON", name=os.path.basename(out), data=main, flag=17, mdat=int(time.time()) + MAC_EPOCH)]
    for name in sorted(files):
        ext = os.path.splitext(name)[1].lower()
        entries.append(dict(type=TYPES.get(ext, b"TEXT"), name=name, data=open(files[name], "rb").read(), mdat=mac_time(files[name])))
    head = doc.header[:-8]   # drop the unfrozen 'ptch' + length; pack() writes the new one
    with open(out, "wb") as f:
        f.write(pack(head, entries))
    return files


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "check":
        for path in args:
            _, entries = read(path)
            print(path)
            for e in entries:
                print("  %-5s %8d  %s%s" % (e["type"].decode("latin1"), len(e["data"]), e["name"], "  (device)" if e["flag"] == 17 else ""))
    elif cmd == "roundtrip":
        bad = 0
        for path in args:
            raw = open(path, "rb").read()
            if b"mx@c" not in raw:
                continue
            ok = pack(*read(path)) == raw
            bad += not ok
            print("ok  " if ok else "DIFF", path)
        sys.exit(1 if bad else 0)
    elif cmd == "freeze":
        files = freeze(args[0], args[1], args[2:])
        print("froze %s -> %s (%d files)" % (args[0], args[1], len(files)))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
