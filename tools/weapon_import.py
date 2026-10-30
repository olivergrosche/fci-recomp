"""Put a glTF model into the games in place of a first-person weapon: the weapon's .xbg with the new
geometry on its bones, and its two textures (re/notes/MODELS.md).

  python -B tools/weapon_import.py <config.json>

then put the output into the archive with tools/dat2.py replace <game>/weaponpack.dat <out> (only the .xbg
and .xbt files are written there; tools/xbt.py todds makes a texture viewable).

The config (paths relative to it):

  {
    "source": "ma5b/scene.gltf",
    "template": "extract/weaponpack",           the weapon archive's files (dat2.py extract)
    "model": "animations/weapons/first/mp5n/mp5n_first.xbg",
    "axes": ["-x", "z", "y"],                   the game's X (muzzle), Y and Z (up) as the glTF's axes
    "scale": 0.0022,                            metres per glTF unit
    "anchor": {"source": [-41.3, 0, -34.4], "target": [0.077, 0.034, 0.0]},
    "drop": [[[-101, -6, -37], [-77, 6, 18]]],  boxes: pieces entirely inside are left out
    "parts": {"b_Magazine": [[[...], [...]]]},  boxes: pieces entirely inside hang on that bone
    "texture": {"size": 1024, "gloss": [120, 225]},
    "out": "out"
  }

Positions in anchor, drop and parts are glTF units with the axes already turned (X the muzzle, Z up), as
`info` prints them. A piece is a connected part of the mesh; pieces in no box hang on the root bone, and
a bone that gets no piece gets one tiny triangle, out of sight. The materials go into one atlas: base
colour plus emission as the diffuse map, (1 - roughness) as its alpha (the games' gloss), the normal maps
with green along +v as the games' (DirectX style): a glTF's point it along -v by the standard and are
flipped, unless "texture": {"normal_y": "down"} says the model's maps are DirectX style already.

  python -B tools/weapon_import.py info <config.json>     the pieces, their sizes and boxes
"""

import argparse
import base64
import io
import json
import math
from pathlib import Path
import struct
import sys

from PIL import Image, ImageChops, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbg  # noqa: E402
import xbt  # noqa: E402

COMPONENT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DXT1, DXT5 = 0x10, 0x12
PAD = 4  # texels around each material's square in the atlas, against bleeding
PLACEHOLDER = 0.0005  # metres: the triangle of a bone without a piece


# --- glTF -------------------------------------------------------------------------------------------


class Gltf:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.suffix.lower() == ".glb":
            raise SystemExit("error: .glb is not read; export as .gltf with its .bin")
        self.g = json.loads(self.path.read_text(encoding="utf-8"))
        self.buffers = [self.uri(b["uri"]) for b in self.g["buffers"]]

    def uri(self, uri):
        if uri.startswith("data:"):
            return base64.b64decode(uri.split(",", 1)[1])
        return (self.path.parent / uri).read_bytes()

    def accessor(self, i):
        a = self.g["accessors"][i]
        view = self.g["bufferViews"][a["bufferView"]]
        n, c = WIDTH[a["type"]], COMPONENT[a["componentType"]]
        size = struct.calcsize(c)
        stride = view.get("byteStride") or n * size
        buf = self.buffers[view["buffer"]]
        at = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        values = [struct.unpack_from(f"<{n}{c}", buf, at + k * stride) for k in range(a["count"])]
        if a.get("normalized") and c != "f":
            top = float((1 << (8 * size - (1 if c.islower() else 0))) - 1)
            values = [tuple(max(v / top, -1.0) for v in t) for t in values]
        return values

    def image(self, texture):
        """a texture's image as Pillow opens it"""
        src = self.g["images"][self.g["textures"][texture["index"]]["source"]]
        if "uri" in src:
            return Image.open(io.BytesIO(self.uri(src["uri"])))
        view = self.g["bufferViews"][src["bufferView"]]
        at = view.get("byteOffset", 0)
        return Image.open(io.BytesIO(self.buffers[view["buffer"]][at : at + view["byteLength"]]))

    def primitives(self):
        """every triangle primitive placed by its nodes: positions, normals, tangents (or None), uvs,
        triangles, material"""
        out = []

        def walk(i, parent):
            node = self.g["nodes"][i]
            m = mat4_mul(parent, node_matrix(node))
            for p in self.g["meshes"][node["mesh"]]["primitives"] if "mesh" in node else ():
                if p.get("mode", 4) != 4:
                    continue
                at = p["attributes"]
                pos = [mat4_point(m, v) for v in self.accessor(at["POSITION"])]
                nrm = [unit(mat4_dir(m, v)) for v in self.accessor(at["NORMAL"])]
                tan = None
                if "TANGENT" in at:
                    tan = [unit(mat4_dir(m, v[:3])) + (v[3],) for v in self.accessor(at["TANGENT"])]
                uv = [v[:2] for v in self.accessor(at["TEXCOORD_0"])]
                idx = [v[0] for v in self.accessor(p["indices"])]
                tris = [tuple(idx[k : k + 3]) for k in range(0, len(idx) - 2, 3)]
                out.append(
                    {
                        "pos": pos,
                        "normal": nrm,
                        "tangent": tan,
                        "uv": uv,
                        "tris": tris,
                        "material": p.get("material", 0),
                        "mirror": det3(m) < 0,
                    }
                )
            for c in node.get("children", ()):
                walk(c, m)

        for root in self.g["scenes"][self.g.get("scene", 0)]["nodes"]:
            walk(root, IDENTITY)
        return out


IDENTITY = tuple(tuple(float(i == j) for j in range(4)) for i in range(4))


def node_matrix(node):
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return tuple(tuple(m[c * 4 + r] for c in range(4)) for r in range(4))
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    r = xbg.quat_matrix((x, y, z, w))
    s = node.get("scale", (1, 1, 1))
    t = node.get("translation", (0, 0, 0))
    return tuple(tuple(r[i][j] * s[j] for j in range(3)) + (t[i],) for i in range(3)) + ((0, 0, 0, 1),)


def mat4_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)) for i in range(4))


def mat4_point(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] + m[i][3] for i in range(3))


def mat4_dir(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def det3(m):
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n > 1e-12 else (0.0, 0.0, 1.0)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


# --- the source in the game's axes, cut into pieces ------------------------------------------------


def axes_matrix(axes):
    """rows: the game's X, Y, Z from the glTF's x, y, z ("-x", "z", "y")"""
    rows = []
    for a in axes:
        sign = -1.0 if a.startswith("-") else 1.0
        k = "xyz".index(a.lstrip("+-"))
        rows.append(tuple(sign * (i == k) for i in range(3)))
    if sorted(r.index(next(c for c in r if c)) for r in rows) != [0, 1, 2]:
        raise SystemExit(f"error: axes {axes} must name x, y and z once each")
    return tuple(rows)


def turned(prims, axes):
    """the primitives with the axes turned; triangles counter-clockwise from the front as in glTF"""
    a = axes_matrix(axes)
    flip = det3(a) < 0
    out = []
    for p in prims:
        q = dict(p)
        q["pos"] = [xbg.mat_vec(a, v) for v in p["pos"]]
        q["normal"] = [xbg.mat_vec(a, v) for v in p["normal"]]
        mirror = flip != p["mirror"]
        if p["tangent"]:
            q["tangent"] = [xbg.mat_vec(a, v[:3]) + (-v[3] if flip else v[3],) for v in p["tangent"]]
        q["tris"] = [(i, k, j) for i, j, k in p["tris"]] if mirror else list(p["tris"])
        out.append(q)
    return out


def pieces(prims):
    """connected pieces over shared positions: per primitive, each triangle's piece number"""
    parent = {}

    def find(x):
        root = x
        while parent.setdefault(root, root) != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    keys = [[tuple(round(c, 3) for c in v) for v in p["pos"]] for p in prims]
    for p, k in zip(prims, keys):
        for t in p["tris"]:
            a = find(k[t[0]])
            for i in t[1:]:
                b = find(k[i])
                if a != b:
                    parent[b] = a
    numbers = {}
    return [[numbers.setdefault(find(k[t[0]]), len(numbers)) for t in p["tris"]] for p, k in zip(prims, keys)]


def piece_boxes(prims, piece):
    boxes = {}
    for p, ids in zip(prims, piece):
        for t, n in zip(p["tris"], ids):
            lo, hi, count = boxes.get(n, ([math.inf] * 3, [-math.inf] * 3, 0))
            for i in t:
                v = p["pos"][i]
                lo = [min(a, b) for a, b in zip(lo, v)]
                hi = [max(a, b) for a, b in zip(hi, v)]
            boxes[n] = (lo, hi, count + 1)
    return boxes


def inside(box, lo, hi):
    return all(box[0][k] <= lo[k] and hi[k] <= box[1][k] for k in range(3))


# --- textures -----------------------------------------------------------------------------------------


def material_maps(gltf, material, cell, flip_green):
    """(diffuse RGB, smoothness L, normal RGB with green along +v as the games') of a material, each
    cell x cell"""
    m = gltf.g["materials"][material] if "materials" in gltf.g else {}
    pbr = m.get("pbrMetallicRoughness", {})

    def load(texture, mode, default):
        if texture is None:
            return Image.new(mode, (cell, cell), default)
        return gltf.image(texture).convert(mode).resize((cell, cell), Image.LANCZOS)

    factor = pbr.get("baseColorFactor", (1, 1, 1, 1))
    base = load(pbr.get("baseColorTexture"), "RGB", (255, 255, 255))
    base = ImageChops.multiply(base, Image.new("RGB", base.size, tuple(round(255 * f) for f in factor[:3])))
    if "emissiveTexture" in m or any(m.get("emissiveFactor", (0, 0, 0))):
        glow = load(m.get("emissiveTexture"), "RGB", (255, 255, 255))
        ef = tuple(round(255 * f) for f in m.get("emissiveFactor", (1, 1, 1)))
        base = ImageChops.add(base, ImageChops.multiply(glow, Image.new("RGB", glow.size, ef)))
    mr = pbr.get("metallicRoughnessTexture")
    rough = load(mr, "RGB", (0, 255, 0)).getchannel("G") if mr else None
    if rough is None:
        rough = Image.new("L", (cell, cell), round(255 * pbr.get("roughnessFactor", 1.0)))
    normal = load(m.get("normalTexture"), "RGB", (128, 128, 255))
    if flip_green and "normalTexture" in m:
        r, g, b = normal.split()
        normal = Image.merge("RGB", (r, ImageOps.invert(g), b))
    return base, ImageOps.invert(rough), normal


def atlas(gltf, materials, size, gloss, flip_green):
    """the diffuse (RGBA) and normal (RGB) atlases and each material's (u0, v0, scale) in it"""
    side = math.ceil(math.sqrt(len(materials)))
    cell = size // side
    pad = max(1, PAD * cell // 512)
    diffuse = Image.new("RGBA", (size, size), (0, 0, 0, gloss[0]))
    normal = Image.new("RGB", (size, size), (128, 128, 255))
    place = {}
    lo, hi = gloss
    for k, mat in enumerate(materials):
        x, y = (k % side) * cell, (k // side) * cell
        base, smooth, nrm = material_maps(gltf, mat, cell, flip_green)
        alpha = smooth.point(lambda v: round(lo + (hi - lo) * v / 255))
        rgba = Image.merge("RGBA", (*base.split(), alpha))
        inner = cell - 2 * pad
        # the whole square first (its edges stand in for the padding), then the texture inset by pad
        diffuse.paste(rgba, (x, y))
        normal.paste(nrm, (x, y))
        diffuse.paste(rgba.resize((inner, inner), Image.LANCZOS), (x + pad, y + pad))
        normal.paste(nrm.resize((inner, inner), Image.LANCZOS), (x + pad, y + pad))
        place[mat] = ((x + pad) / size, (y + pad) / size, inner / size)
    return diffuse, normal, place


def dxt_xbt(image, fmt):
    """an .xbt with all mip levels down to 4x4, DXT compressed by Pillow"""
    levels, im = [], image.convert("RGB" if fmt == DXT1 else "RGBA")
    while True:
        out = io.BytesIO()
        im.save(out, "DDS", pixel_format="DXT5" if fmt == DXT5 else "DXT1")
        levels.append(out.getvalue()[128:])
        if min(im.size) <= 4:
            break
        im = im.resize((im.width // 2, im.height // 2), Image.BOX)
    data = b"".join(levels)
    return xbt.MAGIC + struct.pack("<7I", image.width, image.height, len(data), fmt, len(levels), 1, 0) + data


# --- the weapon -----------------------------------------------------------------------------------------


def frames(p, stats):
    """per vertex (tangent, binormal): the tangent the glTF's or along +u, the binormal along -v as the
    games' (whichever way the glTF's bitangent points; stats counts where it agreed)"""
    n = len(p["pos"])
    acc_t, acc_b = [(0.0, 0.0, 0.0)] * n, [(0.0, 0.0, 0.0)] * n
    for a, b, c in p["tris"]:
        e1, e2 = sub(p["pos"][b], p["pos"][a]), sub(p["pos"][c], p["pos"][a])
        du1, dv1 = sub(p["uv"][b], p["uv"][a])
        du2, dv2 = sub(p["uv"][c], p["uv"][a])
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            continue
        t = tuple((e1[k] * dv2 - e2[k] * dv1) / det for k in range(3))
        bv = tuple(-(e2[k] * du1 - e1[k] * du2) / det for k in range(3))
        for i in (a, b, c):
            acc_t[i] = tuple(x + y for x, y in zip(acc_t[i], t))
            acc_b[i] = tuple(x + y for x, y in zip(acc_b[i], bv))
    out = []
    for k, (nrm, t, bv) in enumerate(zip(p["normal"], acc_t, acc_b)):
        given = p["tangent"][k] if p["tangent"] else None
        if given:
            t = given[:3]
        elif dot(t, t) < 1e-20:  # no uv gradient: any frame
            t = cross(nrm, (0, 0, 1)) if abs(nrm[2]) < 0.9 else cross(nrm, (1, 0, 0))
        tg = unit(sub(t, tuple(dot(t, nrm) * c for c in nrm)))
        b = cross(nrm, tg)
        if dot(bv, bv) > 1e-20:
            if given:
                stats[0] += dot(tuple(c * given[3] for c in b), bv) > 0
                stats[1] += 1
            if dot(b, bv) < 0:
                b = tuple(-c for c in b)
        elif given and given[3] < 0:
            b = tuple(-c for c in b)
        out.append((tg, b))
    return out


def build(cfg, base):
    gltf = Gltf(base / cfg["source"])
    prims = turned(gltf.primitives(), cfg["axes"])
    piece = pieces(prims)
    boxes = piece_boxes(prims, piece)
    stats = [0, 0]
    fr = [frames(p, stats) for p in prims]
    print(
        f"{sum(len(p['tris']) for p in prims)} triangles in {len(boxes)} pieces; the glTF's bitangents point "
        f"along -v at {stats[0]} of {stats[1]} vertices (the binormals written all do)"
    )
    models = cfg.get("models") or [{"model": cfg["model"]}]
    atlases = {}
    for mc in models:
        tex = {**cfg.get("texture", {}), **mc.get("texture", {})}
        if tex.get("normal_y", "up") not in ("up", "down"):
            raise SystemExit('error: texture.normal_y is "up" (the glTF standard) or "down" (DirectX style)')
        key = (tex.get("size", 1024), tuple(tex.get("gloss", (120, 225))), tex.get("normal_y", "up"))
        if key not in atlases:
            atlases[key] = atlas(gltf, sorted({p["material"] for p in prims}), key[0], key[1], key[2] == "up")
        build_model(cfg, mc["model"], base, prims, piece, boxes, fr, atlases[key])


def build_model(cfg, name, base, prims, piece, boxes, fr, maps):
    """one model of the config: the template's .xbg with the glTF on its bones, and its textures"""
    diffuse, normal, place = maps
    folder = base / cfg["template"]
    template = (folder / name).read_bytes()
    model = xbg.Model(template)
    names = [b.name.lower() for b in model.bones]
    drop = cfg.get("drop", [])
    owner = {}  # piece -> bone, None when left out
    for n, (lo, hi, _) in boxes.items():
        owner[n] = None if any(inside(box, lo, hi) for box in drop) else 0
        for bone, bone_boxes in cfg.get("parts", {}).items():  # bones this model lacks stay on the root
            if owner[n] is not None and bone.lower() in names and any(inside(b, lo, hi) for b in bone_boxes):
                owner[n] = names.index(bone.lower())
    scale = cfg["scale"]
    src, dst = cfg["anchor"]["source"], cfg["anchor"]["target"]
    offset = tuple(d - s * scale for s, d in zip(src, dst))

    # each submesh: its part's bone, then its vertices (in the bone's frame) and triangles
    bone_of = {sm.vertex_offset: model.part_of(sm).bone for sm in model.submeshes}
    meshes = {bone: ([], []) for bone in bone_of.values()}
    frame = {bone: model.bone_matrix(bone) for bone in meshes}
    dropped = 0
    for p, ids, f in zip(prims, piece, fr):
        u0, v0, s = place[p["material"]]
        remap = {}
        for tri, n in zip(p["tris"], ids):
            bone = owner[n]
            if bone is None:
                dropped += 1
                continue
            verts, tris = meshes[bone]
            rot, pos = frame[bone]
            back = transpose(rot)
            out = []
            for i in tri:
                if (bone, i) not in remap:
                    world = tuple(c * scale + o for c, o in zip(p["pos"][i], offset))
                    u, v = p["uv"][i]
                    verts.append(
                        {
                            "pos": xbg.mat_vec(back, sub(world, pos)),
                            "uv": (u0 + min(max(u, 0.0), 1.0) * s, v0 + min(max(v, 0.0), 1.0) * s),
                            "normal": xbg.mat_vec(back, p["normal"][i]),
                            "tangent": xbg.mat_vec(back, f[i][0]),
                            "binormal": xbg.mat_vec(back, f[i][1]),
                        }
                    )
                    remap[(bone, i)] = len(verts) - 1
                out.append(remap[(bone, i)])
            a, b, c = out
            tris.append((a, c, b))  # the games' front faces turn the other way
    for verts, tris in meshes.values():
        if not tris:  # a bone without a piece: one tiny triangle at the bone, out of sight
            for q in ((0, 0, 0), (PLACEHOLDER, 0, 0), (0, 0, PLACEHOLDER)):
                verts.append(
                    {"pos": q, "uv": (0.5, 0.5), "normal": (0, -1, 0), "tangent": (1, 0, 0), "binormal": (0, 0, 1)}
                )
            tris.append((0, 1, 2))
    rebuilt = xbg.rebuild(template, [meshes[bone_of[sm.vertex_offset]] for sm in model.submeshes])

    out = base / cfg["out"]
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(rebuilt)
    for path in (t.lstrip("\\").replace("\\", "/").lower() for t in model.textures):
        is_normal = path.endswith("_nt.xbt")
        old = folder / path
        fmt = DXT1 if is_normal or (old.exists() and xbt.header(old.read_bytes())[3] == DXT1) else DXT5
        data = dxt_xbt(normal if is_normal else diffuse, fmt)
        f = out / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    new = xbg.Model(rebuilt)
    print(f"{name}: {dropped} triangles left out")
    for sm in new.submeshes:
        print(
            f"  {model.bones[new.part_of(sm).bone].name}: {len(sm.vertices)} vertices, "
            f"{len(xbg.strip_triangles(sm.strip))} triangles, strip of {len(sm.strip)}"
        )


def transpose(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def info(cfg, base):
    prims = turned(Gltf(base / cfg["source"]).primitives(), cfg["axes"])
    boxes = piece_boxes(prims, pieces(prims))
    lo = [min(b[0][k] for b in boxes.values()) for k in range(3)]
    hi = [max(b[1][k] for b in boxes.values()) for k in range(3)]
    print(
        f"{sum(len(p['tris']) for p in prims)} triangles in {len(boxes)} pieces, "
        f"box {fmt3(lo)} .. {fmt3(hi)} (axes turned, glTF units)"
    )
    for n, (lo, hi, count) in sorted(boxes.items(), key=lambda kv: -kv[1][2]):
        print(f"  piece {n:3d}: {count:6d} triangles, {fmt3(lo)} .. {fmt3(hi)}")


def fmt3(v):
    return "(" + ", ".join(f"{c:.1f}" for c in v) + ")"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("args", nargs="+", metavar="[info] config")
    a = ap.parse_args()
    command, path = ("info", a.args[1]) if a.args[0] == "info" and len(a.args) == 2 else ("build", a.args[0])
    path = Path(path)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    (info if command == "info" else build)(cfg, path.parent)


if __name__ == "__main__":
    main()
