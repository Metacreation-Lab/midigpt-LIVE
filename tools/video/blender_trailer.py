"""
Render the trailer's clean plates (no text, no logo, no fades) in Blender from a plan exported by trailer3.py.

  blender -b -P tools/video/blender_trailer.py -- --plan plan_full.json --tex dist/video/ui3_hd --out plates/full \
      [--section N | --frames A-B] [--res 1920x1080] [--samples 128] [--device GPU|CPU] [--spec javascript/midigpt_panel_spec.js]

World units follow the draft renderer (tools/video/panel3d.py): x = texture px, y = -texture px, z = height in
texture px, all scaled by 1/1000 for Blender. The texture is 1920 x 1280 in px space at any resolution (ui3_hd is
3840 x 2560: UVs are normalized). Frames already on disk are skipped, so a job can be re-queued.
"""
import json
import math
import os
import sys

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PLAN = json.load(open(arg("--plan")))
TEX = arg("--tex")
OUT = arg("--out")
RES = tuple(int(v) for v in arg("--res", "1920x1080").split("x"))
SAMPLES = int(arg("--samples", "128"))
DEVICE = arg("--device", "GPU")
SPEC_JS = arg("--spec", os.path.join(ROOT, "javascript", "midigpt_panel_spec.js"))
S = 0.001                     # px -> metres
K = 2.0                       # px per pt (the texture is 1920 x 1280 for the 960 x 640 pt panel)
TW, TH = 1920.0, 1280.0
EMIT = float(arg("--emit", "0.95"))       # how much of the texture is self-lit (1 = the flat UI colours)
LIGHT = float(arg("--light", "0.8"))      # scales every lamp
SHEEN = float(arg("--sheen", "0.0"))    # the printed surface's sheen (the key light mirrored over the whole plate)
DIFFUSE = float(arg("--diffuse", "0.15"))  # how much light the printed colours catch (low keeps black screens black)
GLOW_GAIN = float(arg("--glow-gain", "4.0"))  # a highlighted part: + texture * glow * this (glow ~0.16 warm at full)


def load_spec():
    s = open(SPEC_JS).read()
    return json.loads(s[s.index("SPEC: ") + 6:s.index(",\n  THEME")])


SPEC = load_spec()


def parts_for(page):
    """Same part list as panel3d.parts_main (name, kind, geometry in pt)."""
    out = []
    m = SPEC["pages"][page]
    if page == "main":
        out += [("POLY", "knob", (105, 387, 26)), ("LENGTH", "knob", (291, 387, 26))]
    for name, cx, cy, r in m["knobs"]:
        if (page != "main" or cx > 384) and name != "SEED":   # SEED is a readout, not a knob
            out.append((name, "knob", (cx, cy, r)))          # the knob body only: its LED ring stays on the panel
    for name, x, y, w, h in m["toggles"]:
        out.append((name, "box", (x, y, w, h)))
    for name, x, y, w, h in m.get("keys", []):
        out.append((name, "box", (x, y, w, h)))
    for name, x, y, w, h in SPEC["top_keys"]:
        out.append((name, "box", (x, y, w, h)))
    o = SPEC["output"]
    for i, (x, y, w, h) in enumerate(o["takes"]):
        out.append(("TAKE%d" % i, "box", (x, y, w, h)))
    out.append(("KEEP", "box", tuple(o["keep"])))
    out.append(("GENERATE", "box", tuple(o["generate"])))
    e = SPEC["extras"]
    for name, cx, cy, r in e["knobs"]:
        out.append((name, "knob", (cx, cy, r)))
    for name, x, y, w, h in e["toggles"]:
        out.append((name, "box", (x, y, w, h)))
    return out


def recesses(page):
    """(x, y, w, h in px, depth px): bays 3 pt deep, the screen 5 pt."""
    out = [(b[0] * K, b[1] * K, b[2] * K, b[3] * K, -3 * K) for b in SPEC["pages"][page]["bays"] + [SPEC["output"]["bay"], SPEC["extras"]["bay"]]]
    sx, sy, sw, sh = SPEC["screen"]
    out.append((sx * K, sy * K, sw * K, sh * K, -5 * K))
    if page == "main":                                   # the seed readout: a small screen in its own dip
        out.append((598 * K, 395 * K, 76 * K, 20 * K, -2 * K))
    return out


# ---------------------------------------------------------------- scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.filter_size = 1.2                       # pixel filter: soft enough to kill stair-stepping on fine UI lines
    if DEVICE == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA", "METAL", "HIP"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                if any(d.type == backend for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == backend
                    sc.cycles.device = "GPU"
                    print("cycles device:", backend, flush=True)
                    break
            except Exception:
                continue
        else:
            sc.cycles.device = "CPU"
            print("cycles device: CPU (no GPU backend)", flush=True)
    else:
        sc.cycles.device = "CPU"
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.012, 0.012, 0.013, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    return sc


def panel_material():
    """The panel's printed surface: the frame's texture as colour, satin finish, a little self-light so the screens
    read like real displays."""
    m = bpy.data.materials.new("Panel")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "PanelTex"
    tex.interpolation = "Cubic"
    tex.extension = "EXTEND"
    uv = nt.nodes.new("ShaderNodeUVMap")
    nt.links.new(uv.outputs[0], tex.inputs[0])
    dif = nt.nodes.new("ShaderNodeMix")
    dif.data_type = "RGBA"
    dif.blend_type = "MULTIPLY"
    dif.inputs[0].default_value = 1.0
    dif.inputs[7].default_value = (DIFFUSE, DIFFUSE, DIFFUSE, 1)
    nt.links.new(tex.outputs[0], dif.inputs[6])
    nt.links.new(dif.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.48
    bsdf.inputs["Specular IOR Level"].default_value = SHEEN
    # self-light: the texture itself, plus the part's highlight (object attribute "glow")
    att = nt.nodes.new("ShaderNodeAttribute")
    att.attribute_type = "OBJECT"
    att.attribute_name = "glow"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "ADD"
    mix.inputs[0].default_value = 1.0
    sc = nt.nodes.new("ShaderNodeMix")
    sc.data_type = "RGBA"
    sc.blend_type = "MULTIPLY"
    sc.inputs[0].default_value = 1.0
    sc.inputs[7].default_value = (EMIT, EMIT, EMIT, 1)
    nt.links.new(tex.outputs[0], sc.inputs[6])
    # the highlight brightens the part's own colours (warm-tinted); a flat added colour turned dark parts into tan blobs
    lit = nt.nodes.new("ShaderNodeMix")
    lit.data_type = "RGBA"
    lit.blend_type = "MULTIPLY"
    lit.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs[0], lit.inputs[6])
    nt.links.new(att.outputs[0], lit.inputs[7])
    gain = nt.nodes.new("ShaderNodeMix")
    gain.data_type = "RGBA"
    gain.blend_type = "MULTIPLY"
    gain.inputs[0].default_value = 1.0
    gain.inputs[7].default_value = (GLOW_GAIN, GLOW_GAIN, GLOW_GAIN, 1)
    nt.links.new(lit.outputs[2], gain.inputs[6])
    nt.links.new(sc.outputs[2], mix.inputs[6])
    nt.links.new(gain.outputs[2], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    return m


def mesh_obj(name, verts, faces, uvs, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x * S, y * S, z * S) for x, y, z in verts], [], faces)
    me.update()
    layer = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            layer.data[li].uv = uvs[vi]
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    ob["glow"] = (0.0, 0.0, 0.0)
    return ob


def uv_of(x, y):
    return (x / TW, 1.0 - y / TH)


def build_plate(page, mat):
    """The panel plate with exact recesses: a grid on every recess edge, each cell flat at its depth, walls between."""
    rs = recesses(page)
    xs = sorted({0.0, TW} | {v for r in rs for v in (r[0], r[0] + r[2])})
    ys = sorted({0.0, TH} | {v for r in rs for v in (r[1], r[1] + r[3])})

    def depth(cx, cy):
        d = 0.0
        for x, y, w, h, z in rs:
            if x <= cx <= x + w and y <= cy <= y + h:
                d = min(d, z)
        return d

    verts, faces, uvs = [], [], []

    def quad(a, b, c, d):
        base = len(verts)
        for (x, y, z) in (a, b, c, d):
            verts.append((x, -y, z))
            uvs.append(uv_of(x, y))
        faces.append((base, base + 1, base + 2, base + 3))

    Z = [[depth((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2) for j in range(len(ys) - 1)] for i in range(len(xs) - 1)]
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1, y0, y1, z = xs[i], xs[i + 1], ys[j], ys[j + 1], Z[i][j]
            quad((x0, y0, z), (x0, y1, z), (x1, y1, z), (x1, y0, z))               # top (normal +z: y is flipped)
            if i + 1 < len(xs) - 1 and Z[i + 1][j] != z:                          # wall to the right neighbour
                z2 = Z[i + 1][j]
                quad((x1, y0, z), (x1, y1, z), (x1, y1, z2), (x1, y0, z2))
            if j + 1 < len(ys) - 1 and Z[i][j + 1] != z:                          # wall to the next row
                z2 = Z[i][j + 1]
                quad((x0, y1, z), (x0, y1, z2), (x1, y1, z2), (x1, y1, z))
    ob = mesh_obj("plate_" + page, verts, faces, uvs, mat)
    # a body under the plate, so the panel has thickness at its edges
    bpy.ops.mesh.primitive_cube_add(size=1)
    body = bpy.context.object
    body.name = "body_" + page
    floor = min([r[4] for r in rs] + [0.0]) - 2          # its top stays under the deepest recess, or it covers them
    body.scale = (TW * S, TH * S, 40 * S)
    body.location = (TW / 2 * S, -TH / 2 * S, (floor - 20) * S)
    body.data.materials.append(dark_material())
    body["glow"] = (0.0, 0.0, 0.0)
    return [ob, body]


_DARK = None


def dark_material():
    global _DARK
    if _DARK is None:
        _DARK = bpy.data.materials.new("Body")
        _DARK.use_nodes = True
        b = _DARK.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.03, 0.03, 0.032, 1)
        b.inputs["Roughness"].default_value = 0.6
    return _DARK


def build_knob(name, cx, cy, r, mat):
    """A cylinder with a softened top edge; its top shows the texture under it (rotates with the knob)."""
    seg, rings = 64, 4
    H = 14 * K
    verts, faces, uvs = [], [], []
    verts.append((cx, -cy, H)); uvs.append(uv_of(cx, cy))
    prof = [(1.0 - 0.06 * (1 - math.cos(math.pi / 2 * k / rings)), H - 6 * K * (k / rings) ** 3) for k in range(1, rings + 1)] + [(1.0, 0.0)]
    for rf, z in prof:
        for s in range(seg):
            a = 2 * math.pi * s / seg
            x, y = cx + r * K * rf * math.cos(a), cy + r * K * rf * math.sin(a)
            # the side takes its colour from just inside the rim, never from the panel around the knob (the LED ring)
            ru = r * K * min(rf, 0.92)
            verts.append((x, -y, z)); uvs.append(uv_of(cx + ru * math.cos(a), cy + ru * math.sin(a)))
    for s in range(seg):
        faces.append((0, 1 + s, 1 + (s + 1) % seg))
    for ring in range(len(prof) - 1):
        a0, b0 = 1 + ring * seg, 1 + (ring + 1) * seg
        for s in range(seg):
            faces.append((a0 + s, b0 + s, b0 + (s + 1) % seg, a0 + (s + 1) % seg))
    ob = mesh_obj("part_" + name, verts, faces, uvs, mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob["center"] = (cx * K * S, -cy * K * S)
    return ob


def build_box(name, x, y, w, h, mat):
    H = 6 * K
    x0, y0, x1, y1 = x * K, y * K, (x + w) * K, (y + h) * K
    corners = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
    verts, faces, uvs = [], [], []
    for (cx, cy) in corners:
        verts.append((cx, -cy, H)); uvs.append(uv_of(cx, cy))
    for (cx, cy) in corners:
        verts.append((cx, -cy, 0.0)); uvs.append(uv_of(cx, cy))
    faces.append((0, 1, 2, 3))
    for k in range(4):
        a, b = k, (k + 1) % 4
        faces.append((a, a + 4, b + 4, b))
    ob = mesh_obj("part_" + name, verts, faces, uvs, mat)
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width = 0.6 * K * S
    bev.segments = 2
    return ob


def build(page, mat):
    objs = build_plate(page, mat)
    parts = {}
    for name, kind, g in parts_for(page):
        if kind == "knob":
            # the knob mesh is built around its centre so it can rotate in place
            cx, cy, r = g
            ob = build_knob(name, 0.0, 0.0, r, mat)
            ob.location = (cx * K * S, -cy * K * S, 0.0)
            # UVs must stay where the knob sits on the panel: rebuild them at the real position
            layer = ob.data.uv_layers[0]
            for poly in ob.data.polygons:
                for li in poly.loop_indices:
                    v = ob.data.vertices[ob.data.loops[li].vertex_index].co
                    layer.data[li].uv = uv_of(v.x / S + cx * K, -(v.y / S) + cy * K)
        else:
            ob = build_box(name, *g, mat)
        parts[name] = ob
        objs.append(ob)
    return objs, parts


def lights():
    def area(name, loc, rot, size, energy, color=(1, 1, 1)):
        d = bpy.data.lights.new(name, "AREA")
        d.size = size
        d.energy = energy * LIGHT
        d.color = color
        o = bpy.data.objects.new(name, d)
        o.location = loc
        o.rotation_euler = rot
        bpy.context.collection.objects.link(o)
    area("key", (0.2, 0.6, 2.2), (math.radians(-25), math.radians(-20), 0), 2.5, 260)
    area("fill", (2.2, -2.6, 1.4), (math.radians(60), math.radians(30), 0), 3.0, 90, (0.95, 0.97, 1.0))
    area("rim", (0.96, 1.0, 0.6), (math.radians(-70), 0, 0), 2.0, 120, (1.0, 0.92, 0.85))


def place_camera(cam, c):
    pos = mathutils.Vector([c["pos"][0] * S, c["pos"][1] * S, c["pos"][2] * S])
    look = mathutils.Vector([c["look"][0] * S, c["look"][1] * S, c["look"][2] * S])
    cam.location = pos
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (look - pos).to_track_quat("-Z", "Y")
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.angle = math.radians(c["fov"])


def main():
    sc = reset()
    mat = panel_material()
    texnode = mat.node_tree.nodes["PanelTex"]
    pages = {}
    for page in ("main", "engine", "setup"):
        objs, parts = build(page, mat)
        pages[page] = (objs, parts)
    lights()
    cd = bpy.data.cameras.new("cam")
    cd.clip_start = 0.01
    cd.clip_end = 100
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    rest = {n: (ob.location.copy(), ob.rotation_euler.copy()) for pg in pages.values() for n, ob in pg[1].items()}

    frames = PLAN["frames"]
    if arg("--section") is not None:
        a, b = PLAN["sections"][arg("--section")]
    elif arg("--frames"):
        a, b = (int(v) for v in arg("--frames").split("-"))
    else:
        a, b = 0, len(frames) - 1
    os.makedirs(OUT, exist_ok=True)
    images = {}
    for i in range(a, b + 1):
        f = frames[i]
        path = os.path.join(OUT, "f%05d.png" % i)
        if f["logo"] or os.path.exists(path):
            continue
        for page, (objs, parts) in pages.items():                  # only the frame's page is visible
            for ob in objs:
                ob.hide_render = page != f["page"]
        if f["tex"] not in images:
            if len(images) > 6:                                  # keep memory flat over long sections
                for im in images.values():
                    bpy.data.images.remove(im)
                images.clear()
            images[f["tex"]] = bpy.data.images.load(os.path.join(TEX, f["tex"]))
        texnode.image = images[f["tex"]]
        objs, parts = pages[f["page"]]
        for name, ob in parts.items():
            loc, rot = rest[name] if name in rest else (ob.location, ob.rotation_euler)
            ob.location = (loc.x, loc.y, f["lift"].get(name, 0.0) * S)
            # a knob turns about its axis (the texture under the panel stays; the knob's printed top turns with it)
            ob.rotation_euler = (0.0, 0.0, -math.radians(f["rot"].get(name, 0.0)))
            g = f["glow"].get(name, [0.0, 0.0, 0.0])
            ob["glow"] = (g[0] * 1.6, g[1] * 1.6, g[2] * 1.6)
        place_camera(cam, f["cam"])
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print("frame", i, "done", flush=True)


main()
