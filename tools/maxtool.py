#!/usr/bin/env python3
"""
maxtool -- inspect, validate and safely rewrite Max patches (.maxpat) and
Max for Live devices (.amxd) from the command line.

An .amxd is a small binary chunk header ("ampf" ... "ptch" <len>) followed
by the same JSON a .maxpat holds. load()/save() keep that header intact and
fix up the ptch length field, so every script in this repo should go
through them instead of re-implementing the byte juggling.

Usage:
  python3 tools/maxtool.py summary   <file>...      object/param/line counts
  python3 tools/maxtool.py tree      <file>          boxes per (sub)patcher
  python3 tools/maxtool.py params    <file>          Live parameters + visibility
  python3 tools/maxtool.py validate  <file>...      structural checks (exit 1 on error)
  python3 tools/maxtool.py deps      <file>          dependency_cache entries
  python3 tools/maxtool.py find      <file> <text>   boxes whose text/varname contains <text>

Library:
  from maxtool import load, save, walk, find_box
  doc = load(path); ...mutate doc.data...; save(doc)
"""

import json
import os
import sys
from collections import Counter

VISIBILITY = {0: "automated+stored", 1: "stored only", 2: "hidden"}


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Doc:
    def __init__(self, path, data, header=b"", trailer=b""):
        self.path = path
        self.data = data
        self.header = header
        self.trailer = trailer

    @property
    def patcher(self):
        return self.data["patcher"]

    @property
    def is_amxd(self):
        return self.path.endswith(".amxd")


def load(path):
    raw = open(path, "rb").read()
    start = raw.find(b"{")
    if start < 0:
        raise ValueError(f"{path}: no JSON payload found")
    header = raw[:start]
    text = raw[start:].decode("utf-8")
    data, consumed = json.JSONDecoder().raw_decode(text)
    trailer = raw[start + len(text[:consumed].encode("utf-8")):]
    if path.endswith(".amxd"):
        declared = int.from_bytes(header[-4:], "little")
        actual = len(text[:consumed].encode("utf-8")) + len(trailer)
        if declared != actual:
            raise ValueError(f"{path}: ptch length {declared} != payload {actual}; unknown header layout")
    return Doc(path, data, header, trailer)


def _scalar(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return "null"
    return repr(v) if isinstance(v, float) else str(v)


def _max_json(v, depth):
    """Serialize the way Max itself writes patchers (tabs, ' : ', inline
    scalar arrays, '}\\n,' separators) so re-saved files diff cleanly
    against files saved from the Max editor."""
    if isinstance(v, dict):
        tabs = "\t" * depth
        entries = [f'{tabs}\t{json.dumps(k, ensure_ascii=False)} : {_max_json(x, depth + 1)}' for k, x in v.items()]
        return f"{tabs}{{\n" + ",\n".join(entries) + f"\n{tabs}}}\n"
    if isinstance(v, list):
        if not v:
            return "[  ]"
        return "[ " + ", ".join(_max_json(x, depth + 1) if isinstance(x, (dict, list)) else _scalar(x) for x in v) + " ]"
    return _scalar(v)


def dumps(data):
    return _max_json(data, 0)


def save(doc, path=None):
    path = path or doc.path
    text = dumps(doc.data)
    if doc.is_amxd or path.endswith(".amxd"):
        body = text.rstrip("\n").encode("utf-8")
        header = bytearray(doc.header)
        header[-4:] = (len(body) + len(doc.trailer)).to_bytes(4, "little")
        out = bytes(header) + body + doc.trailer
    else:
        out = text.encode("utf-8")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, path)


def walk(patcher, path=()):
    """Yield (path, patcher) for a patcher and every embedded subpatcher."""
    yield path, patcher
    for bx in patcher.get("boxes", []):
        b = bx["box"]
        if "patcher" in b:
            yield from walk(b["patcher"], path + (b["id"],))


def boxes(patcher):
    for path, p in walk(patcher):
        for bx in p.get("boxes", []):
            yield path, bx["box"]


def find_box(patcher, box_id=None, varname=None):
    for path, b in boxes(patcher):
        if (box_id and b.get("id") == box_id) or (varname and b.get("varname") == varname):
            return b
    return None


def label(b):
    if b["maxclass"] == "newobj":
        return b.get("text", "")
    return f'{b["maxclass"]} {b.get("varname", "")} {b.get("text", "")}'.strip()


def param_info(b):
    """(longname, visibility) for a parameter-enabled box, else None."""
    if not b.get("parameter_enable"):
        sa = b.get("saved_object_attributes", {})
        if not sa.get("parameter_enable"):
            return None
    v = b.get("saved_attribute_attributes", {}).get("valueof", {})
    return v.get("parameter_longname", b.get("varname", "?")), v.get("parameter_invisible", 0)


# ---------------------------------------------------------------- commands

def cmd_summary(paths):
    for path in paths:
        doc = load(path)
        kinds, nlines, params = Counter(), 0, Counter()
        for _, p in walk(doc.patcher):
            nlines += len(p.get("lines", []))
            for bx in p.get("boxes", []):
                b = bx["box"]
                kinds[b.get("text", "").split(" ")[0] if b["maxclass"] == "newobj" else b["maxclass"]] += 1
                pi = param_info(b)
                if pi:
                    params[VISIBILITY.get(pi[1], pi[1])] += 1
        print(f"== {path}")
        print(f"   boxes={sum(kinds.values())} lines={nlines} params={dict(params)}")
        print("   " + ", ".join(f"{k}:{v}" for k, v in kinds.most_common(25)))


def cmd_tree(path):
    doc = load(path)
    for p_path, p in walk(doc.patcher):
        print(f"[{'/'.join(p_path) or 'root'}]")
        for bx in p.get("boxes", []):
            b = bx["box"]
            extra = f" -> {b['name']}" if b["maxclass"] == "bpatcher" else ""
            pres = " (pres)" if b.get("presentation") else ""
            print(f"  {b['id']:<28} {label(b)[:80]}{extra}{pres}")


def cmd_params(path):
    doc = load(path)
    for p_path, b in boxes(doc.patcher):
        pi = param_info(b)
        if pi:
            print(f"{'/'.join(p_path) or 'root'}::{b['id']:<24} {b['maxclass']:<13} {pi[0]:<28} {VISIBILITY.get(pi[1], pi[1])}")
    if doc.is_amxd:
        n = len([k for k in doc.patcher.get("parameters", {}) if k.startswith("obj-")])
        print(f"-- device parameters block: {n} entries")


def validate(doc):
    errors, warnings = [], []
    for p_path, p in walk(doc.patcher):
        where = "/".join(p_path) or "root"
        ids = {}
        for bx in p.get("boxes", []):
            b = bx["box"]
            if b["id"] in ids:
                errors.append(f"[{where}] duplicate id {b['id']}")
            ids[b["id"]] = b
        for ln in p.get("lines", []):
            pl = ln["patchline"]
            (src, so), (dst, di) = pl["source"], pl["destination"]
            if src not in ids:
                errors.append(f"[{where}] line from missing box {src}")
                continue
            if dst not in ids:
                errors.append(f"[{where}] line to missing box {dst}")
                continue
            if so >= ids[src].get("numoutlets", 0):
                # js/jsui/bpatcher outlet counts are only known at runtime
                level = warnings if ids[src]["maxclass"] in ("bpatcher", "jsui") or ids[src].get("text", "").startswith(("js ", "p ")) else errors
                level.append(f"[{where}] {src} outlet {so} >= numoutlets {ids[src].get('numoutlets')}")
            if di >= ids[dst].get("numinlets", 0):
                level = warnings if ids[dst]["maxclass"] in ("bpatcher", "jsui") or ids[dst].get("text", "").startswith(("js ", "p ")) else errors
                level.append(f"[{where}] {dst} inlet {di} >= numinlets {ids[dst].get('numinlets')}")
    names = Counter()
    for _, b in boxes(doc.patcher):
        pi = param_info(b)
        if pi:
            names[pi[0]] += 1
    for n, c in names.items():
        if c > 1:
            warnings.append(f"parameter longname '{n}' used {c}x (Max will rename)")
    for dep in doc.patcher.get("dependency_cache", []):
        bp = dep.get("bootpath", "")
        if bp and not os.path.expanduser(bp).startswith(REPO_ROOT):
            warnings.append(f"dependency outside repo: {dep['name']} @ {bp}")
    if doc.is_amxd:
        valid = set()
        def collect(p, prefix):
            for bx in p.get("boxes", []):
                b = bx["box"]
                key = prefix + b["id"]
                valid.add(key)
                if "patcher" in b:
                    collect(b["patcher"], key + "::")
        collect(doc.patcher, "")
        for k in doc.patcher.get("parameters", {}):
            if k.startswith("obj-") and k.split("::")[0] not in valid:
                warnings.append(f"stale device parameter entry {k}")
    return errors, warnings


def cmd_validate(paths):
    bad = False
    for path in paths:
        errors, warnings = validate(load(path))
        status = "FAIL" if errors else "ok"
        print(f"{status:4} {path}  ({len(errors)} errors, {len(warnings)} warnings)")
        for e in errors:
            print("   E", e)
        for w in warnings:
            print("   w", w)
        bad |= bool(errors)
    sys.exit(1 if bad else 0)


def cmd_deps(path):
    for dep in load(path).patcher.get("dependency_cache", []):
        print(f"{dep['name']:<32} {dep.get('type',''):<5} {dep.get('bootpath','')}")


def cmd_find(path, needle):
    doc = load(path)
    for p_path, b in boxes(doc.patcher):
        if needle in label(b) or needle in b.get("name", ""):
            print(f"{'/'.join(p_path) or 'root'}::{b['id']}  {label(b)[:100]}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, args = sys.argv[1], sys.argv[2:]
    {"summary": lambda: cmd_summary(args),
     "tree": lambda: cmd_tree(args[0]),
     "params": lambda: cmd_params(args[0]),
     "validate": lambda: cmd_validate(args),
     "deps": lambda: cmd_deps(args[0]),
     "find": lambda: cmd_find(args[0], args[1])}[cmd]()
