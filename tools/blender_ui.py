"""
Build the MIDI-GPT panel as a real 3D scene in Blender and render it with Cycles:
the static panel (one background image) and a knob filmstrip (one frame per
angle). Layout comes from tools/render_ui.py; live data (notes, value rings,
legends) is drawn on top afterwards by `render_ui.py compose`.

Every part is a solid made from a 2D profile (inset, height) swept around a
rounded rectangle, so edges are true geometry: a slow S-curve swell, a
quarter round, a chamfer, a dome or a dish. Recesses (screen, pockets, wells,
seams) are cut from the panel with one boolean.

  Blender -b -P tools/blender_ui.py -- panel <style> <out.png> [samples]
  Blender -b -P tools/blender_ui.py -- knob  <style> <out_dir> [frames]
"""

import math
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_ui as L  # noqa: E402  layout only

W, H = L.W, L.H
KEY_POWER = float(os.environ.get("MIDIGPT_KEY", "30"))

# ---------------------------------------------------------------- palette / materials
GREY = dict(base=0.50, plate=0.56, knob=0.70, key=0.68, lit=0.035, screen=0.012, ink=0.02, metal=0.62, dark=0.06)


def mat(name, v, rough=0.55, metal=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (v, v, v, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.08
    b.inputs["Specular IOR Level"].default_value = spec
    return m


def materials():
    return dict(
        base=mat("base", GREY["base"], 0.62),
        plate=mat("plate", GREY["plate"], 0.58),
        knob=mat("knob", GREY["knob"], 0.32),
        knob_gloss=mat("knob_gloss", GREY["knob"], 0.22, coat=0.6),
        key=mat("key", GREY["key"], 0.36),
        lit=mat("lit", GREY["lit"], 0.38),
        screen=mat("screen", GREY["screen"], 0.32),
        ink=mat("ink", GREY["ink"], 0.6),
        metal=mat("metal", GREY["metal"], 0.28, metal=1.0),
        dark=mat("dark", GREY["dark"], 0.5),
    )


# ---------------------------------------------------------------- profiles: lists of (inset, z)
def ease(kind, t):
    if kind == "soft":
        return t * t * t * (t * (t * 6 - 15) + 10)
    if kind == "flare":   # starts flat and accelerates: a wide, progressive rise
        return t * t * (3 - 2 * t) ** 1.0 * (0.6 + 0.4 * t)
    if kind == "round":
        return math.sqrt(max(0.0, 1 - (1 - t) ** 2))
    return t  # chamfer


def rise(inset0, z0, width, height, kind, n=10):
    return [(inset0 + width * (i / n), z0 + height * ease(kind, i / n)) for i in range(1, n + 1)]


def dome(inset0, z0, radius, amount, n=10):
    """Top of a disc whose remaining radius is `radius`: dome (amount>0) or dish (<0) to the centre."""
    pts = []
    for i in range(1, n + 1):
        t = i / n
        pts.append((inset0 + radius * t, z0 + amount * (1 - (1 - t) ** 2)))
    return pts


# ---------------------------------------------------------------- mesh builder
def ring(cx, cy, w, h, r, d, corner_segs):
    hw, hh = w / 2 - d, h / 2 - d
    rr = max(min(r - d, hw, hh), 0.02)
    hw, hh = max(hw, 0.03), max(hh, 0.03)
    pts = []
    for (qx, qy, a0) in ((hw - rr, hh - rr, 0), (-(hw - rr), hh - rr, 90), (-(hw - rr), -(hh - rr), 180), (hw - rr, -(hh - rr), 270)):
        for k in range(corner_segs):
            a = math.radians(a0 + 90 * k / (corner_segs - 1))
            pts.append((cx + qx + rr * math.cos(a), cy + qy + rr * math.sin(a)))
    return pts


def solid(name, cx, cy, w, h, r, profile, mats, corner_segs=16, knurl=None, smooth=True):
    """profile: [(inset, z, mat_index)] from the outside bottom up; closed with a fan at the top."""
    verts, faces, fmats = [], [], []
    rings = []
    for (d, z, mi) in profile:
        pts = ring(cx, cy, w, h, r, d, corner_segs)
        idx = []
        for (x, y) in pts:
            if knurl and knurl[0] <= z <= knurl[1]:
                a = math.atan2(y - cy, x - cx)
                k = knurl[2] * (0.5 + 0.5 * math.cos(a * knurl[3]))
                x, y = x - k * math.cos(a), y - k * math.sin(a)
            idx.append(len(verts))
            verts.append((x, -y, z))
        rings.append((idx, mi))
    n = len(rings[0][0])
    flat = []
    for i in range(len(rings) - 1):
        a, b, mi = rings[i][0], rings[i + 1][0], rings[i + 1][1]
        lvl = abs(profile[i][1] - profile[i + 1][1]) < 1e-4
        for k in range(n):
            faces.append((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
            fmats.append(mi)
            flat.append(lvl)
    top, mi = rings[-1]
    c = len(verts)
    verts.append((cx, -cy, profile[-1][1]))
    for k in range(n):
        faces.append((top[k], top[(k + 1) % n], c))
        fmats.append(mi)
        flat.append(True)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for m in mats:
        me.materials.append(m)
    for f, mi, fl in zip(me.polygons, fmats, flat):
        f.material_index = mi
        f.use_smooth = smooth and not fl
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if not smooth:
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
    if smooth:
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
    return ob


def raised(name, x, y, w, h, r, height, width, kind, m, z0=0.0, top=None, corner_segs=16):
    """A rounded box rising from z0. top: ('dish'|'dome', amount) applied over the flat top."""
    prof = [(0, z0 - 2, 0), (0, z0, 0)] + [(d, z, 0) for (d, z) in rise(0, z0, width, height, kind, 12)]
    if top:
        rem = min(w, h) / 2 - width
        prof += [(d, z, 0) for (d, z) in dome(width, z0 + height, rem * 0.92, top[1])]
    return solid(name, x + w / 2, y + h / 2, w, h, r, prof, [m], corner_segs)


def cutter(name, x, y, w, h, r, depth, width, kind, corner_segs=16, z0=0.0):
    """Pocket shape for the boolean: flares out at surface z0, flat floor at z0 - depth."""
    prof = [(-width, z0 + 3, 0), (-width, z0, 0)]
    for i in range(1, 13):
        t = i / 12
        prof.append((-width + width * t, z0 - depth * ease(kind, t), 0))
    return solid(name, x + w / 2, y + h / 2, w, h, r, prof, [bpy.data.materials["base"]], corner_segs, smooth=True)


def disc_cutter(name, cx, cy, rad, depth, width, kind, z0=0.0):
    return cutter(name, cx - rad, cy - rad, 2 * rad, 2 * rad, rad, depth, width, kind, corner_segs=40, z0=z0)


def groove_cutter(name, x, y, w, h, r, gw, depth, z0=0.0, corner_segs=16):
    """A thin seam around a rounded rectangle, built directly as a closed ring-shaped solid."""
    cx, cy = x + w / 2, y + h / 2
    o = ring(cx, cy, w + gw, h + gw, r + gw / 2, 0, corner_segs)
    i = ring(cx, cy, w + gw, h + gw, r + gw / 2, gw, corner_segs)
    n = len(o)
    zt, zb = z0 + 3, z0 - depth
    verts = [(px, -py, zt) for px, py in o] + [(px, -py, zt) for px, py in i] + \
            [(px, -py, zb) for px, py in o] + [(px, -py, zb) for px, py in i]
    OT, IT, OB, IB = 0, n, 2 * n, 3 * n
    faces = []
    for k in range(n):
        k2 = (k + 1) % n
        faces += [(OT + k, OT + k2, IT + k2, IT + k), (OB + k, IB + k, IB + k2, OB + k2),
                  (OT + k, OB + k, OB + k2, OT + k2), (IT + k, IT + k2, IB + k2, IB + k)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    me.materials.append(bpy.data.materials["base"])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def cut_all(target, cutters):
    col = bpy.data.collections.new("cutters")
    bpy.context.scene.collection.children.link(col)
    for c in cutters:
        for uc in list(c.users_collection):
            uc.objects.unlink(c)
        col.objects.link(c)
    bo = target.modifiers.new("cut", "BOOLEAN")
    bo.operation = "DIFFERENCE"
    bo.solver = "EXACT"
    bo.operand_type = "COLLECTION"
    bo.collection = col
    col.hide_render = True


# ---------------------------------------------------------------- knob
def knob(st, cx, cy, R, value, M, z0):
    k = st["knob"]
    prof, knurl = [(0, z0 - 2, 0), (0, z0, 0)], None
    mats = [M[n] for n in k["mats"]]
    kind = k["kind"]
    if kind == "pillow":     # wide swelling skirt, then a raised cap with a soft dome
        Rs, Rc = 1.25 * R, 0.80 * R
        prof += [(d, z, 0) for (d, z) in rise(0, z0, 0.42 * R, 0.30 * R, "soft", 14)]
        prof += [(Rs - Rc - 0.02 * R, z0 + 0.30 * R, 0)]
        prof += [(d, z, 1) for (d, z) in rise(Rs - Rc - 0.02 * R, z0 + 0.30 * R, 0.13 * R, 0.30 * R, "round", 10)]
        prof += [(d, z, 1) for (d, z) in dome(Rs - Rc + 0.11 * R, z0 + 0.60 * R, Rc - 0.11 * R, 0.05 * R, 12)]
        outer = Rs
    elif kind == "cylinder":  # Braun: straight wall, small round edge, dished top
        prof += [(0, z0 + 0.62 * R, 0)] + [(d, z, 0) for (d, z) in rise(0, z0 + 0.62 * R, 0.08 * R, 0.08 * R, "round", 8)]
        prof += [(d, z, 1) for (d, z) in dome(0.08 * R, z0 + 0.70 * R, 0.92 * R, -0.07 * R, 12)]
        outer = R
    elif kind == "stepped":   # console: metal skirt, knurled grip, metal cap
        prof += [(0, z0 + 0.06 * R, 0), (0.06 * R, z0 + 0.14 * R, 0), (0.22 * R, z0 + 0.14 * R, 0), (0.24 * R, z0 + 0.16 * R, 1)]
        prof += [(0.24 * R, z0 + 0.60 * R, 1)] + [(d, z, 1) for (d, z) in rise(0.24 * R, z0 + 0.60 * R, 0.05 * R, 0.06 * R, "round", 6)]
        prof += [(0.31 * R, z0 + 0.66 * R, 2), (0.36 * R, z0 + 0.74 * R, 2), (0.36 * R + 0.001, z0 + 0.74 * R, 2)]
        prof += [(d, z, 2) for (d, z) in dome(0.36 * R, z0 + 0.74 * R, 0.80 * R, 0.0, 4)]
        knurl = (z0 + 0.15 * R, z0 + 0.62 * R, 0.035 * R, 48)
        outer = 1.16 * R
    elif kind == "well":      # carved: soft dome rising out of a well
        prof += [(d, z, 0) for (d, z) in rise(0, z0, 0.40 * R, 0.36 * R, "soft", 14)]
        prof += [(d, z, 0) for (d, z) in dome(0.40 * R, z0 + 0.36 * R, 0.60 * R, 0.10 * R, 12)]
        outer = R
    else:                     # monolith: low turned disc
        prof += [(0, z0 + 0.06 * R, 0)] + [(d, z, 0) for (d, z) in rise(0, z0 + 0.06 * R, 0.05 * R, 0.05 * R, "round", 6)]
        prof += [(d, z, 0) for (d, z) in dome(0.05 * R, z0 + 0.11 * R, 0.95 * R, 0.035 * R, 12)]
        outer = R
    ob = solid("knob", 0, 0, 2 * outer, 2 * outer, outer, prof, mats, corner_segs=48, knurl=knurl)
    # pointer, built pointing up (+y), then the whole knob turns; it sits on the surface at its radius
    pk, u0, u1, hw = k["pointer"]
    def z_at(rad):
        return min(prof, key=lambda q: abs((outer - q[0]) - rad))[1]
    if pk == "dot":
        zt = z_at(u0 * R)
        p = solid("ptr", 0, -u0 * R, 2 * hw * R, 2 * hw * R, hw * R, [(0, zt - 1.5, 0), (0, zt + 0.12, 0)], [M["ink"]], 10, smooth=False)
    else:
        zt = max(z_at(u0 * R), z_at(u1 * R))
        L_ = (u1 - u0) * R
        p = solid("ptr", 0, -(u0 * R + L_ / 2), 2 * hw * R, L_, hw * R, [(0, zt - 1.5, 0), (0, zt + 0.12, 0)], [M["ink"]], 6, smooth=False)
    p.parent = ob
    ob.location = (cx, -cy, 0)
    ob.rotation_euler.z = -math.radians(-135 + 270 * value)
    return ob


# ---------------------------------------------------------------- styles (geometry only; palette is shared)
STYLES = {
    "softform": dict(panel="plates", plate=(2.6, 16, "soft", 16), screen=(4.5, 7, "soft", 14),
                     knob=dict(kind="pillow", mats=["plate", "knob"], pointer=("line", 0.2, 0.62, 0.045)),
                     key=dict(shape="pill", h=3.6, w=0.5, kind="soft", lit_press=0.45)),
    "braun": dict(panel="flat", screen=(3.0, 2.0, "round", 8),
                  knob=dict(kind="cylinder", mats=["knob", "knob"], pointer=("dot", 0.62, 0, 0.085)),
                  key=dict(shape="round", h=4.0, w=0.14, kind="round", top=("dish", -0.5), lit_press=1.0)),
    "functional_a": dict(panel="flat", screen=(3.0, 2.0, "round", 8),
                         knob=dict(kind="cylinder", mats=["knob", "knob"], pointer=("dot", 0.62, 0, 0.085)),
                         key=dict(cap=dict(r=3.5, h=4.0, taper=1.0, rt=1.1, lit_dark=1))),
    "functional_b": dict(panel="flat", screen=(3.0, 2.0, "round", 8),
                         knob=dict(kind="cylinder", mats=["knob", "knob"], pointer=("dot", 0.62, 0, 0.085)),
                         key=dict(cap=dict(r="stadium", h=3.4, taper=0.4, rt=1.6, dome=0.7, lit_dark=1))),
    "functional_c": dict(panel="flat", screen=(3.0, 2.0, "round", 8),
                         knob=dict(kind="cylinder", mats=["knob", "knob"], pointer=("dot", 0.62, 0, 0.085)),
                         key=dict(cap=dict(r=2.0, h=1.8, taper=0.25, rt=0.6))),
    "console": dict(panel="seams", screen=(3.0, 1.2, "round", 8),
                    knob=dict(kind="stepped", mats=["metal", "dark", "metal"], pointer=("line", 0.1, 0.72, 0.035)),
                    key=dict(shape="square", h=3.2, w=0.09, kind="round", lit_press=1.0)),
    "carved": dict(panel="pockets", pockets=(4.0, 4.0, "soft", 12), screen=(4.5, 3.5, "soft", 12), wells=(1.42, 0.30, 0.22),
                   knob=dict(kind="well", mats=["knob"], pointer=("line", 0.25, 0.7, 0.05)),
                   key=dict(shape="well", h=3.0, w=0.3, kind="soft", lit_press=0.5)),
    "monolith": dict(panel="slab", screen=(2.5, 1.0, "round", 8), knob_gap=1.6,
                     knob=dict(kind="disc", mats=["metal"], pointer=("dot", 0.72, 0, 0.07)),
                     key=dict(shape="flush", h=0.8, w=0.06, kind="round", lit_press=1.0)),
}


def key_obj(st, M, x, y, w, h, lit, z0, cut):
    k = st["key"]
    r = {"pill": min(w, h) / 2, "round": 6, "square": 2.5, "well": 6, "flush": 4}[k["shape"]]
    m = M["lit"] if (lit and k["lit_press"] < 1) else M["key"]
    hgt = k["h"] * (k["lit_press"] if lit else 1.0)
    width = max(0.6, k["w"] * min(w, h))
    if k.get("cap"):
        return keycap(k["cap"], M["lit"] if lit and k["cap"].get("lit_dark") else M["key"], x, y, w, h, z0)
    if k["shape"] == "well":
        cut.append(cutter("kw", x - 3, y - 3, w + 6, h + 6, r + 3, 3.5, 2.5, "soft", z0=z0))
        return raised("key", x, y, w, h, r, hgt, width, k["kind"], m, z0 - 3.5)
    if k["shape"] == "flush":
        cut.append(groove_cutter("kg", x, y, w, h, r, 1.3, 1.6, z0=z0))
        return raised("key", x + 0.8, y + 0.8, w - 1.6, h - 1.6, r, hgt, width, k["kind"], m, z0 - 0.5)
    return raised("key", x, y, w, h, r, hgt, width, k["kind"], m, z0, top=k.get("top"))


def keycap(c, m, x, y, w, h, z0):
    """A key built like a real cap: a straight, slightly drafted wall, a small rounded top edge,
    then a flat or gently domed top (domes only on stadium / round caps, so no creases)."""
    r = min(w, h) / 2 if c["r"] == "stadium" else c["r"]
    hh, taper, rt = c["h"], c["taper"], c["rt"]
    prof = [(0, z0 - 2, 0), (0, z0, 0)]
    for i in range(1, 5):
        t = i / 4
        prof.append((taper * t, z0 + (hh - rt) * t, 0))
    prof += [(d, z, 0) for (d, z) in rise(taper, z0 + hh - rt, rt, rt, "round", 10)]
    if c.get("dome") and c["r"] == "stadium":
        prof += [(d, z, 0) for (d, z) in dome(taper + rt, z0 + hh, min(w, h) / 2 - taper - rt, c["dome"], 10)]
    return solid("key", x + w / 2, y + h / 2, w, h, r, prof, [m], 24 if c["r"] == "stadium" else 12)


def build_panel(st, M):
    cut = []
    # panel slab
    slab = raised("panel", -20, -20, W + 40, H + 40, 2, 20, 1, "round", M["base"], -20)
    sd, sw, sk, sr = st["screen"]
    x, y, w, h = L.SCREEN
    cut.append(cutter("screen_c", x, y, w, h, sr, sd, sw, sk))
    glass = raised("glass", x + sw, y + sw, w - 2 * sw, h - 2 * sw, max(sr - sw, 2), 0.05, 0.05, "chamfer", M["screen"], -sd + 0.01)
    level = 0.0
    pm = st["panel"]
    if pm == "plates":
        ph_, pw_, pk_, pr_ = st["plate"]
        for (px, py, pw, ph) in L.PLATES:
            raised("plate", px, py, pw, ph, pr_, ph_, pw_, pk_, M["plate"], 0)
        level = ph_
    elif pm == "pockets":
        pd_, pw_, pk_, pr_ = st["pockets"]
        for (px, py, pw, ph) in L.PLATES:
            cut.append(cutter("pocket", px, py, pw, ph, pr_, pd_, pw_, pk_))
        level = -pd_
    elif pm == "seams":
        for (px, py, pw, ph) in L.PLATES:
            cut.append(groove_cutter("seam", px, py, pw, ph, 4, 1.4, 1.8))
    # keys
    for (kx, ky, kw, kh, lab, lit, ts) in L.KEYS:
        key_obj(st, M, kx, ky, kw, kh, lit, 0 if ky < 40 else level, cut)
    for (sx, sy, sw_, sh_, v) in L.steps_rects():
        key_obj(st, M, sx, sy, sw_, sh_, v, level, cut)
    gx, gy, gw, gh = L.GENERATE
    key_obj(st, M, gx, gy, gw, gh, 0, level, cut)
    # knobs (and their wells / gaps)
    for (cx, cy, r, v, lab, en) in L.KNOBS:
        z0 = level
        if st.get("wells"):
            rm, dm, wm = st["wells"]
            cut.append(disc_cutter("well", cx, cy, r * rm, r * dm, r * wm, "soft", z0=level))
            z0 = level - r * dm
        if st.get("knob_gap"):
            cut.append(groove_cutter("gap", cx - r - 0.5, cy - r - 0.5, 2 * r + 1, 2 * r + 1, r + 0.5, st["knob_gap"], 2.0, z0=level, corner_segs=40))
        knob(st, cx, cy, r, v, M, z0)
    # one boolean for every recess
    if cut:
        cut_all(slab, cut)


# ---------------------------------------------------------------- scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup(width_pt, height_pt, cx, cy, px_w, px_h, samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 4
    sc.render.resolution_x, sc.render.resolution_y = px_w, px_h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = max(width_pt, height_pt)
    cam.clip_end = 3000
    co = bpy.data.objects.new("cam", cam)
    co.location = (cx, -cy, 1000)
    sc.collection.objects.link(co)
    sc.camera = co
    # studio light: one large softbox up and to the left (gives surfaces a gentle falloff and a soft
    # highlight), a weak sun fill from the right, a dim grey environment
    span = max(width_pt, height_pt)
    ld = bpy.data.lights.new("softbox", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = 1.6 * span, 0.9 * span
    ld.energy = KEY_POWER * span * span
    lo = bpy.data.objects.new("softbox", ld)
    lo.location = (cx - 0.35 * span, -cy + 0.85 * span, 1.1 * span)
    sc.collection.objects.link(lo)
    tgt = bpy.data.objects.new("aim", None)
    tgt.location = (cx, -cy, 0)
    sc.collection.objects.link(tgt)
    tc = lo.constraints.new("TRACK_TO"); tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
    fd = bpy.data.lights.new("fill", "SUN")
    fd.energy = 0.35
    fd.angle = math.radians(70)
    fo = bpy.data.objects.new("fill", fd)
    fo.rotation_euler = (math.radians(60), 0, math.radians(-110))
    sc.collection.objects.link(fo)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.42, 0.42, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    sc.world = world


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode, style, out = argv[0], argv[1], argv[2]
    st = STYLES[style]
    reset()
    M = materials()
    if mode == "panel":
        samples = int(argv[3]) if len(argv) > 3 else 64
        setup(W, H, W / 2, H / 2, W * 2, H * 2, samples)
        build_panel(st, M)
        bpy.context.scene.render.filepath = out
        bpy.ops.render.render(write_still=True)
    else:
        frames = int(argv[3]) if len(argv) > 3 else 64
        R, pad = 25, 18
        fw = 2 * (R + pad)
        setup(fw, fw, 0, 0, fw * 2, fw * 2, 24)
        level = 0.0
        floor_m = M["plate"] if st["panel"] == "plates" else M["base"]
        if st["panel"] == "plates":
            level = st["plate"][0]
        raised("floor", -fw, -fw, 2 * fw, 2 * fw, 1, 20, 1, "round", floor_m, level - 20)
        z0 = level
        if st.get("wells"):
            rm, dm, wm = st["wells"]
            slab = bpy.data.objects["floor"]
            cut_all(slab, [disc_cutter("well", 0, 0, R * rm, R * dm, R * wm, "soft", z0=level)])
            z0 = level - R * dm
        if st.get("knob_gap"):
            slab = bpy.data.objects["floor"]
            cut_all(slab, [groove_cutter("gap", -R - 0.5, -R - 0.5, 2 * R + 1, 2 * R + 1, R + 0.5, st["knob_gap"], 2.0, z0=level, corner_segs=40)])
        ob = knob(st, 0, 0, R, 0.0, M, z0)
        os.makedirs(out, exist_ok=True)
        for i in range(frames):
            ob.rotation_euler.z = -math.radians(-135 + 270 * i / (frames - 1))
            bpy.context.scene.render.filepath = os.path.join(out, "f%03d.png" % i)
            bpy.ops.render.render(write_still=True)



if __name__ == "__main__" and "blender_ui.py" in " ".join(sys.argv):
    main()
