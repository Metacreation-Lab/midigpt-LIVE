"""
Path-trace the panel's device assets in Blender from the fields tools/video/asset_fields.py dumps: each asset's exact
heightfield becomes a mesh (one vertex per pixel) with its albedo / gloss / metal / emission as attributes, under an
orthographic camera that maps one pixel to one pixel. Only the lighting changes; sizes and sprite pads are the
exporter's.

  blender -b -P tools/video/blender_panel_assets.py -- --fields dist/assets/fields --out dist/assets/raw \
      [--only bg_main,knob_26] [--samples 256] [--device GPU|CPU] [--exposure 1.0]

Writes <out>/<asset>.exr (backgrounds) or <asset>_a.exr / <asset>_b.exr (sprites: with / without the part), linear,
each also as .npy (h x w x 3, top row first);
tools/video/finish_panel_assets.py turns them into the PNGs the device loads.
"""
import math
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


FIELDS = arg("--fields")
OUT = arg("--out")
ONLY = set(arg("--only").split(",")) if arg("--only") else None
SAMPLES = int(arg("--samples", "256"))
DEVICE = arg("--device", "GPU")
EXPOSURE = float(arg("--exposure", "0.0"))
SKY = float(arg("--sky", "0.06"))           # ambient sky: low, or the gloss-black knobs mirror it and go grey
KEY_E = float(arg("--key", "5.0"))         # key sun strength
KEY_ANGLE = float(arg("--key-angle", "25")) # its size in degrees: soft shadows like the lo-fi drop shadow
FILL_E = float(arg("--fill", "0.8"))
SATIN = float(arg("--satin", "6.5"))        # specular level per unit of the exporter's ks on satin (shin < 100) surfaces
# the exporter's key light (image coordinates: x right, y down) and its fill; Blender's y points up
KEY = (-0.35, 0.75, 0.95)
FILL = (0.7, -0.15, 0.6)


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.render.resolution_percentage = 100
    sc.render.filter_size = 1.0
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = EXPOSURE
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.render.image_settings.color_mode = "RGB"
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
    w = bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = SKY
    for name, d, energy, angle in (("key", KEY, KEY_E, KEY_ANGLE), ("fill", FILL, FILL_E, 30.0)):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(angle)
        o = bpy.data.objects.new(name, ld)
        v = np.array(d, np.float64)
        v /= np.linalg.norm(v)
        o.rotation_mode = "QUATERNION"
        import mathutils
        o.rotation_quaternion = mathutils.Vector(v.tolist()).to_track_quat("Z", "Y")   # a sun shines along its -Z
        sc.collection.objects.link(o)
    cd = bpy.data.cameras.new("cam")
    cd.type = "ORTHO"
    cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam


def material():
    m = bpy.data.materials.new("Field")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]

    def att(name, out):
        n = nt.nodes.new("ShaderNodeAttribute")
        n.attribute_type = "GEOMETRY"
        n.attribute_name = name
        return n.outputs[out]
    nt.links.new(att("alb", "Color"), b.inputs["Base Color"])
    nt.links.new(att("rough", "Fac"), b.inputs["Roughness"])
    nt.links.new(att("spec", "Fac"), b.inputs["Specular IOR Level"])
    nt.links.new(att("metal", "Fac"), b.inputs["Metallic"])
    nt.links.new(att("emis", "Color"), b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    return m


def field_mesh(f, prefix, mat):
    hf = f[prefix + "hf"]
    h, w = hf.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    co = np.stack([xs + 0.5, -(ys + 0.5), hf], -1).reshape(-1, 3)
    idx = np.arange(h * w).reshape(h, w)
    quads = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], -1).reshape(-1, 4)
    me = bpy.data.meshes.new("field")
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4))
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    me.update()

    def put(name, vals, kind):
        a = me.attributes.new(name, kind, "POINT")
        a.data.foreach_set("color" if kind == "FLOAT_COLOR" else "value", vals.ravel())

    def rgba(x):
        return np.concatenate([x.reshape(-1, 3), np.ones((h * w, 1), np.float32)], 1)
    put("alb", rgba(f[prefix + "alb"]), "FLOAT_COLOR")
    put("emis", rgba(f[prefix + "emis"]), "FLOAT_COLOR")
    # the exporter's Phong exponent -> GGX roughness; its specular weight -> Principled's specular level
    # (below 100 the exporter adds a broad satin sheen -- keys, plate -- so those get the wide lobe; gloss stays tight)
    shin = f[prefix + "shin"]
    put("rough", np.where(shin < 100, (2.0 / (shin + 2.0)) ** 0.25, (2.0 / (shin + 2.0)) ** 0.5), "FLOAT")
    put("spec", np.clip(f[prefix + "ks"] * np.where(shin < 100, SATIN, 1.2), 0, 1), "FLOAT")
    put("metal", f[prefix + "metal"], "FLOAT")
    ob = bpy.data.objects.new("field", me)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob, w, h


def render(sc, cam, ob, w, h, path):
    sc.render.resolution_x, sc.render.resolution_y = w, h
    cam.data.ortho_scale = max(w, h)
    cam.data.sensor_fit = "AUTO"
    cam.location = (w / 2, -h / 2, 500)
    cam.rotation_euler = (0, 0, 0)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(ob)
    im = bpy.data.images.load(path)                     # also as a linear float array (top row first) for numpy
    px = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(px)
    np.save(path[:-4] + ".npy", px.reshape(h, w, 4)[::-1, :, :3])
    bpy.data.images.remove(im)
    print("wrote", path, flush=True)


def main():
    sc, cam = setup()
    mat = material()
    os.makedirs(OUT, exist_ok=True)
    for fn in sorted(os.listdir(FIELDS)):
        if not fn.endswith(".npz"):
            continue
        name = fn[:-4]
        if ONLY and name not in ONLY:
            continue
        f = np.load(os.path.join(FIELDS, fn))
        if "hf" in f:
            ob, w, h = field_mesh(f, "", mat)
            render(sc, cam, ob, w, h, os.path.join(OUT, name + ".exr"))
        else:
            for part in ("a", "b"):
                ob, w, h = field_mesh(f, part + "_", mat)
                render(sc, cam, ob, w, h, os.path.join(OUT, "%s_%s.exr" % (name, part)))


main()
