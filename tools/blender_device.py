"""
Hi-fi renders of the device window in Blender (Cycles), in one theme's colours.

Per page: a plate (the panel surface only: sections, screen pockets, toggle
slots, engraved logo), then every moving part rendered alone in place with the
same lighting (knobs; keys up and pushed; toggle thumbs), so the front end can
move, press and dim them. Each part render also writes an object mask; the
`compose` step turns part + mask + plate into an RGBA sprite whose shadow is
alpha (1 - part/plate luminance outside the part).

  python3 tools/blender_device.py job <theme> <page> <job.json>       (system python)
  Blender -b -P tools/blender_device.py -- <job.json> <out_dir> [samples]
  python3 tools/blender_device.py compose <out_dir> <page> [...]       (system python)
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W, H, LVL = 960, 640, -0.1
PAD = (14, 14, 10, 28)          # sprite margin around a part, pt: left, right, top, bottom (shadow falls down)
KEY_H, KEY_H_DOWN = 3.4, 2.2


# ---------------------------------------------------------------- parts (shared by both sides)
def parts_for(spec, page):
    """(id, kind, geometry) for every moving part visible on a page. Ids carry position AND size, so a part that
    changes size is re-rendered instead of reusing a stale render at the same spot."""
    out = []
    p = spec["pages"][page]
    for (name, cx, cy, r) in p["knobs"] + spec["extras"]["knobs"]:
        out.append(("knob_%d_%d_%d" % (cx, cy, r), "knob", (cx, cy, r)))
    for (name, x, y, w, h) in p["toggles"] + spec["extras"]["toggles"]:
        for state in ("off", "on"):
            out.append(("thumb_%d_%d_%dx%d_%s" % (x, y, w, h, state), "thumb", (x, y, w, h, state)))
    keys = [tuple(k[1:5]) for k in spec["top_keys"]] + [tuple(k[1:5]) for k in p["keys"]]
    keys += [tuple(k) for k in spec["output"]["takes"] + spec["output"].get("pages", [])] + [tuple(spec["output"]["keep"]), tuple(spec["output"]["generate"])]
    if spec["extras"].get("steps"):
        sx, sy, n, sw, sh = spec["extras"]["steps"]
        keys += [(sx + i * (sw + 3) + (i // 4) * 3, sy, sw, sh) for i in range(n)]
    for (x, y, w, h) in keys:
        for state in ("up", "down"):
            out.append(("key_%d_%d_%dx%d_%s" % (round(x), y, w, h, state), "key", (x, y, w, h, state)))
    return out


def bbox(kind, g):
    if kind == "knob":
        cx, cy, r = g
        return cx - r, cy - r, cx + r, cy + r
    if kind == "thumb":
        x, y, w, h, state = g
        tw, th = w * 0.76, h * 1.3
        tx = x - 2 if state == "off" else x + w - tw + 2
        return tx, y + h / 2 - th / 2, tx + tw, y + h / 2 + th / 2
    x, y, w, h, _ = g
    return x, y, x + w, y + h


def region(kind, g):
    x0, y0, x1, y1 = bbox(kind, g)
    return (max(0, math.floor(x0 - PAD[0])), max(0, math.floor(y0 - PAD[2])),
            min(W, math.ceil(x1 + PAD[1])), min(H, math.ceil(y1 + PAD[3])))


# ---------------------------------------------------------------- system python: job + fields + compose
def write_job(theme, page, path):
    import frontend_assets as FA
    spec = json.loads(open(os.path.join(os.path.dirname(path), "spec.js")).read().split("=", 1)[1].strip().rstrip(";"))
    th = FA.THEMES[theme]
    job = dict(theme=theme, page=page, render=th["render"], knob_mat=th.get("knob_mat"), spec=spec)
    export_fields(th, spec, page, os.path.splitext(path)[0])
    json.dump(job, open(path, "w"))
    print("job", path)


def export_fields(th, spec, page, stem):
    """The panel surface as maps (height in pt, albedo, roughness, metal, specular) from the same height-field
    model as the quick renderer, so the plate matches it exactly. Toggle slots are left 'off'; the front end
    fills the ones that are on."""
    import numpy as np
    from PIL import Image
    import render_ui as R
    import frontend_assets as FA
    R.use_palette(R.STYLES["cockpit"])
    R.P.update(th["render"])
    S = R.S
    c = R.Canvas(960 * S, 640 * S, R.P["base"], R.MATTE)
    R.engrave_logo(c)
    p = spec["pages"][page]
    for (x, y, w, h, _) in [tuple(b) for b in p["bays"]] + [tuple(spec["output"]["bay"]), tuple(spec["extras"]["bay"])]:
        c.rrect(x * S, y * S, w * S, h * S, 12 * S, 1.2 * S, 3.0 * S, "trench", R.P["plate"], R.MATTE, 0, sink=True)
    FA.screen_pocket(c, *spec["screen"], big=True)
    FA.screen_pocket(c, *spec["output"]["stats"])
    FA.screen_pocket(c, *spec["extras"]["rhythm"])
    for (_, x, y, w, h) in p["screens"]:
        FA.screen_pocket(c, x, y, w, h)
    for (name, x, y, w, h) in p["toggles"] + spec["extras"]["toggles"]:
        FA.slot(c, x, y, w, h, FA.LVL)
    np.save(stem + "_height.npy", (c.hf / S).astype(np.float32))
    alb = np.clip(c.alb * c.grain[..., None], 0, 1) ** (1 / 2.2)
    Image.fromarray((alb * 255 + 0.5).astype(np.uint8), "RGB").save(stem + "_albedo.png")
    rough = np.clip(0.62 - 0.0028 * c.shin, 0.12, 0.7)
    Image.fromarray((rough * 255 + 0.5).astype(np.uint8), "L").save(stem + "_rough.png")
    Image.fromarray((np.clip(c.metal, 0, 1) * 255 + 0.5).astype(np.uint8), "L").save(stem + "_metal.png")
    scr = R.lin(R.hexc(th["render"]["screen"]))
    is_screen = np.all(np.abs(c.alb - scr) < 1e-4, axis=-1)
    Image.fromarray((np.where(is_screen, 0.0, 0.5) * 255 + 0.5).astype(np.uint8), "L").save(stem + "_spec.png")


def blur_px(a, sigma):
    """Separable gaussian blur (numpy only)."""
    import numpy as np
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, mode="valid"), 0, a)
    return np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode="edge"), k, mode="valid"), 1, a)


def compose(out_dir, pages):
    """raw part renders + masks + the page plate -> RGBA sprites with shadow as alpha; writes hifi.js."""
    import numpy as np
    from PIL import Image
    d = os.path.abspath(out_dir)
    while not os.path.exists(os.path.join(d, "spec.js")):
        d = os.path.dirname(d)
    spec = json.loads(open(os.path.join(d, "spec.js")).read().split("=", 1)[1].strip().rstrip(";"))
    theme = os.path.basename(os.path.dirname(os.path.abspath(out_dir)))
    meta_path = os.path.join(out_dir, "hifi.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    S = 2
    lum = lambda im: im[..., 0] * 0.3 + im[..., 1] * 0.59 + im[..., 2] * 0.11
    for page in pages:
        plate = np.asarray(Image.open(os.path.join(out_dir, "hifi_%s.png" % page)).convert("RGB")).astype(np.float32) / 255
        for (pid, kind, g) in parts_for(spec, page):
            raw_p = os.path.join(out_dir, "raw", pid + ".png")
            mask_p = os.path.join(out_dir, "raw", pid + "_mask.png")
            if pid in meta or not os.path.exists(raw_p) or not os.path.exists(mask_p):
                continue
            x0, y0, x1, y1 = region(kind, g)
            X = np.asarray(Image.open(raw_p).convert("RGB")).astype(np.float32) / 255
            M = np.asarray(Image.open(mask_p).convert("L")).astype(np.float32) / 255
            P = plate[y0 * S:y0 * S + X.shape[0], x0 * S:x0 * S + X.shape[1]]
            if P.shape[:2] != X.shape[:2] or M.shape != X.shape[:2]:
                print("size mismatch", pid, X.shape, P.shape, M.shape)
                continue
            shade = np.clip((1 - lum(X) / np.maximum(lum(P), 1e-3) - 0.015) / 0.985, 0, 1)
            a = M + (1 - M) * shade
            hh, ww = a.shape   # feather the border so a clipped shadow never shows as a box
            fy = np.minimum(np.arange(hh), np.arange(hh)[::-1])[:, None] / (6.0 * S)
            fx = np.minimum(np.arange(ww), np.arange(ww)[::-1])[None, :] / (6.0 * S)
            a = M + (a - M) * np.clip(np.minimum(fx, fy), 0, 1)
            rgb = X * M[..., None]   # outside the part the sprite is a pure black shadow
            out = np.dstack([np.where(a[..., None] > 1e-4, rgb / np.maximum(a[..., None], 1e-4), 0), a])
            Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out_dir, pid + ".png"), optimize=True)
            meta[pid] = [x0, y0]
        print("composed", page, len(meta))
    json.dump(meta, open(meta_path, "w"))
    with open(os.path.join(out_dir, "hifi.js"), "w") as f:
        f.write("window.HIFI = window.HIFI || {}; window.HIFI[%s] = %s;\n" % (json.dumps(theme), json.dumps(meta)))


if len(sys.argv) > 1 and sys.argv[1] == "job":
    write_job(sys.argv[2], sys.argv[3], sys.argv[4])
    sys.exit(0)
if len(sys.argv) > 1 and sys.argv[1] == "compose":
    compose(sys.argv[2], sys.argv[3:])
    sys.exit(0)

# ---------------------------------------------------------------- Blender side
import bpy  # noqa: E402
import blender_ui as BU  # noqa: E402


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(name, hexcol, rough=0.5, metal=0.0, coat=0.0, coat_rough=0.08, spec=0.5):
    h = hexcol.lstrip("#")
    rgb = [srgb_to_lin(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgb + [1]
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    b.inputs["Specular IOR Level"].default_value = spec
    return m


def flare(t):
    A, WALL, K = 0.14, 0.2, 3.4
    t = max(0.0, min(1.0, t))
    if t < A:
        return WALL * math.sqrt(max(0.0, 1 - (1 - t / A) ** 2))
    u = (t - A) / (1 - A)
    return WALL + (1 - WALL) * (math.exp(K * u) - 1 - K * u) / (math.exp(K) - 1 - K)


def knob(cx, cy, r, m):
    height, width = 0.40 * r, 0.36 * r
    prof = [(0, LVL - 2, 0), (0, LVL, 0)] + [(width * i / 40, LVL + height * flare(i / 40), 0) for i in range(1, 41)]
    return BU.solid("knob", cx, cy, 2 * r, 2 * r, r, prof, [m], corner_segs=64)


def surface(stem):
    """A grid mesh at 0.5 pt spacing displaced by the height map, textured with the albedo/rough/metal/spec maps."""
    import numpy as np
    hf = np.load(stem + "_height.npy")
    rows, cols = hf.shape
    xs = np.arange(cols, dtype=np.float32) * (W / cols) + 0.5 * W / cols
    ys = np.arange(rows, dtype=np.float32) * (H / rows) + 0.5 * H / rows
    X, Y = np.meshgrid(xs, ys)
    co = np.stack([X, -Y, hf], axis=-1).reshape(-1, 3)
    idx = np.arange(rows * cols).reshape(rows, cols)
    q = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1)
    nf = (rows - 1) * (cols - 1)
    me = bpy.data.meshes.new("surface")
    me.vertices.add(rows * cols)
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(nf * 4)
    me.loops.foreach_set("vertex_index", q.astype(np.int32))
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(nf, dtype=bool))
    m = bpy.data.materials.new("surface")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / W, 1 / H, 1)
    mp.inputs["Location"].default_value = (0, 1, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    for suffix, socket, colour in (("_albedo.png", "Base Color", True), ("_rough.png", "Roughness", False),
                                   ("_metal.png", "Metallic", False), ("_spec.png", "Specular IOR Level", False)):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(stem + suffix)
        tex.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], b.inputs[socket])
    me.materials.append(m)
    ob = bpy.data.objects.new("surface", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_parts(job):
    col = job["render"]
    km = job.get("knob_mat") or (30, 0.12, 0)
    gloss = km[0] >= 120
    M = dict(knob=mat("knob", col["knob"], 0.16 if gloss else 0.32, coat=0.9 if gloss else 0.3, coat_rough=0.05),
             key=mat("key", col["key"], 0.3, coat=0.4, coat_rough=0.12))
    objs = []
    for (pid, kind, g) in parts_for(job["spec"], job["page"]):
        if kind == "knob":
            ob = knob(g[0], g[1], g[2], M["knob"])
        elif kind == "thumb":
            tx, ty, tx1, ty1 = bbox(kind, g)
            th = ty1 - ty
            ob = BU.raised("thumb", tx, ty, tx1 - tx, th, th / 2, 3.2, 0.3, "round", M["knob"], LVL)
        else:
            x, y, w, h, state = g
            ob = BU.raised("key", x, y, w, h, 3.5, KEY_H if state == "up" else KEY_H_DOWN, 1.2, "round", M["key"], 0 if y < 40 else LVL)
        ob.pass_index = 1
        ob.hide_render = True
        objs.append((pid, kind, g, ob))
    return objs


def mask_output(sc, folder):
    """Compositor: write the object-index mask of pass 1 next to every render."""
    bpy.context.view_layer.use_pass_object_index = True
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    idm = nt.nodes.new("CompositorNodeIDMask")
    idm.index = 1
    idm.use_antialiasing = True
    nt.links.new(rl.outputs["IndexOB"], idm.inputs[0])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = folder
    fo.format.file_format = "PNG"
    fo.format.color_mode = "BW"
    nt.links.new(idm.outputs[0], fo.inputs[0])
    return fo


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    job = json.load(open(argv[0]))
    out = argv[1]
    samples = int(argv[2]) if len(argv) > 2 else 128
    only = os.environ.get("MIDIGPT_ONLY")   # comma list of part ids, for tests
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    BU.reset()
    BU.setup(W, H, W / 2, H / 2, W * 2, H * 2, samples)
    sc = bpy.context.scene
    sc.cycles.max_bounces = 6
    sc.render.use_persistent_data = True
    w_ = sc.world.node_tree.nodes["Background"]
    w_.inputs["Color"].default_value = (0.5, 0.5, 0.52, 1)
    w_.inputs["Strength"].default_value = float(os.environ.get("MIDIGPT_WORLD", "0.3"))
    lo = bpy.data.objects["softbox"]
    span = max(W, H)
    lo.data.size, lo.data.size_y = 0.7 * span, 0.4 * span
    lo.location = (W / 2 - 0.12 * span, -H / 2 + 1.05 * span, 0.8 * span)
    lo.data.energy = float(os.environ.get("MIDIGPT_KEY", "30")) * span * span
    sc.view_settings.exposure = float(os.environ.get("MIDIGPT_EXPOSURE", "-0.45"))
    surface(os.path.splitext(argv[0])[0])
    objs = build_parts(job)
    fo = mask_output(sc, raw)

    plate = os.path.join(out, "hifi_%s.png" % job["page"])
    if not os.path.exists(plate):   # the surface alone, full frame
        sc.render.use_border = False
        fo.mute = True
        sc.render.filepath = plate
        bpy.ops.render.render(write_still=True)
        print("plate", plate, flush=True)

    fo.mute = False
    sc.render.use_border = True
    sc.render.use_crop_to_border = True
    sc.cycles.samples = max(32, samples // 2)
    for (pid, kind, g, ob) in objs:
        if (only and pid not in only.split(",")) or os.path.exists(os.path.join(raw, pid + "_mask.png")):
            continue
        x0, y0, x1, y1 = region(kind, g)
        sc.render.border_min_x, sc.render.border_max_x = x0 / W, x1 / W
        sc.render.border_min_y, sc.render.border_max_y = 1 - y1 / H, 1 - y0 / H
        ob.hide_render = False
        fo.file_slots[0].path = pid + "_mask_"
        sc.render.filepath = os.path.join(raw, pid + ".png")
        bpy.ops.render.render(write_still=True)
        ob.hide_render = True
        written = os.path.join(raw, pid + "_mask_%04d.png" % sc.frame_current)
        if os.path.exists(written):
            os.replace(written, os.path.join(raw, pid + "_mask.png"))
        print("part", pid, flush=True)


if "--" in sys.argv:
    main()
