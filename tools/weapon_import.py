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
    "texture": {"size": 1024, "gloss": [120, 225], "gain": 1.0},
    "out": "out"
  }

Positions in anchor, drop and parts are glTF units with the axes already turned (X the muzzle, Z up), as
`info` prints them. A piece is a connected part of the mesh; pieces in no box hang on the weapon's frame
(the bone of its largest submesh, or "frame": "<bone>"), and a bone that gets no piece gets one tiny
triangle, out of sight. The materials go into one atlas: base
colour plus emission as the diffuse map, (1 - roughness) as its alpha (the games' gloss), the normal maps
with green along +v as the games' (DirectX style): a glTF's point it along -v by the standard and are
flipped, unless "texture": {"normal_y": "down"} says the model's maps are DirectX style already.
"gain" brightens the base colour (Halo's maps are made for an engine that multiplies them with the light: about
1.8 for its UNSC weapons). Materials with the same maps share their square of the atlas; a material whose
texture coordinates span several repeats of its texture gets them tiled in its square (at most 4 a side).

More keys:

    "models": [{"model": "...first.xbg", "texture": {"size": 1024}}, {"model": "...3rd.xbg", ...}]
                                                several models from one config; an entry may also give its own
                                                source, axes, rotate, scale, anchor, drop, parts, keep, frame,
                                                position_scale, drop_materials, double_sided (a third-person
                                                model from a world model, a model turned another way), and
                                                template and out (a model from another archive: "out" may
                                                list several folders, one per archive that holds it)
    "rotate": [0, 26, 0]                        degrees about the game's X, Y, Z (in that order), about the
                                                anchor, after the axes
    "drop": ["frame bullet", [[...], [...]]]    an entry is a box or the name of a glTF node (all of its
    "parts": {"b_Magazine": ["frame magazine"]} triangles, whatever pieces they touch); so in parts
    "keep": ["b_Shell"]                         bones that keep the template's own geometry (a part with
                                                textures of its own, such as a shotgun shell)
    "drop_materials": ["gauge"]                 glTF materials (by name) left out
    "double_sided": ["blade"]                   glTF materials (by name) drawn from both sides: the games
                                                draw one, so their triangles get a back
    "materials": {"needles": {"color": [230, 60, 200]}, "decal": {"under": [200, 180, 90]}}
                                                a material's diffuse as one flat colour; or its base map laid
                                                over a flat colour by its alpha (a cut-out decal: the games
                                                draw it opaque)
    "position_scale": "fit"                     metres per int16 step: the finest power-of-two multiple of
                                                1/32767 that holds the model (default: the template's)

The new geometry and its two textures go to the material of the template's largest submesh: each bone's
geometry into its submesh with that material's textures; the bone's other submeshes (scope glass, a
suppressor, a shell with a texture of its own) get the tiny triangle and their textures stay as they are,
as they may be another model's too.

  python -B tools/weapon_import.py info <config.json>     the pieces, their sizes, boxes and glTF nodes
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
MAX_TILES = 4  # repeats of a texture per side in its square of the atlas


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
                        "node": node.get("name", f"node {i}"),
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


def selects(entry, prim, lo, hi):
    """a drop or parts entry: a glTF node's name, or a box the piece (lo .. hi) lies inside"""
    return prim["node"].lower() == entry.lower() if isinstance(entry, str) else inside(entry, lo, hi)


def material_name(gltf, material):
    return gltf.g["materials"][material].get("name", "") if "materials" in gltf.g else ""


def back_faces(p):
    """a primitive's back: the triangles turned around, the normals reversed (the games draw one side)"""
    q = dict(p)
    q["normal"] = [tuple(-c for c in n) for n in p["normal"]]
    if p["tangent"]:
        q["tangent"] = [t[:3] + (-t[3],) for t in p["tangent"]]
    q["tris"] = [(a, c, b) for a, b, c in p["tris"]]
    return q


def rotation(degrees):
    """the rotation by (x, y, z) degrees about the game's X, then Y, then Z"""
    m = IDENTITY3
    for axis, d in enumerate(degrees):
        c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
        i, j = (axis + 1) % 3, (axis + 2) % 3  # right-handed: a positive angle turns i towards j
        r = [[float(a == b) for b in range(3)] for a in range(3)]
        r[i][i], r[i][j], r[j][i], r[j][j] = c, -s, s, c
        m = xbg.mat_mul(tuple(map(tuple, r)), m)
    return m


IDENTITY3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def source(cfg, base):
    """the config's glTF in the game's axes: primitives (without the dropped materials), each triangle's
    piece, the pieces' boxes and each vertex's (tangent, binormal)"""
    gltf = Gltf(base / cfg["source"])
    leave = {m.lower() for m in cfg.get("drop_materials", ())}
    prims = [
        p for p in turned(gltf.primitives(), cfg["axes"]) if material_name(gltf, p["material"]).lower() not in leave
    ]
    both = {m.lower() for m in cfg.get("double_sided", ())}
    prims += [back_faces(p) for p in prims if material_name(gltf, p["material"]).lower() in both]
    piece = pieces(prims)
    boxes = piece_boxes(prims, piece)
    stats = [0, 0]
    fr = [frames(p, stats) for p in prims]
    repeated = {m: r for m, r in tiles(prims).items() if r != (0, 0, 1, 1)}
    print(
        f"{cfg['source']}: {sum(len(p['tris']) for p in prims)} triangles in {len(boxes)} pieces; the glTF's "
        f"bitangents point along -v at {stats[0]} of {stats[1]} vertices (the binormals written all do)"
        + "".join(
            f"; {material_name(gltf, m)!r} spans {a} x {d} repeats of its texture from ({u}, {v})"
            for m, (u, v, a, d) in repeated.items()
        )
    )
    return gltf, prims, piece, boxes, fr


# --- textures -----------------------------------------------------------------------------------------


def material_maps(gltf, material, cell, flip_green, gain=1.0, override=None):
    """(diffuse RGB, smoothness L, normal RGB with green along +v as the games') of a material, each
    cell x cell; override {"color": (r, g, b)} in place of its base colour and emission, {"under": (r, g, b)}
    beneath its base map by its alpha"""
    override = override or {}
    m = gltf.g["materials"][material] if "materials" in gltf.g else {}
    pbr = m.get("pbrMetallicRoughness", {})

    def load(texture, mode, default):
        if texture is None:
            return Image.new(mode, (cell, cell), default)
        return gltf.image(texture).convert(mode).resize((cell, cell), Image.LANCZOS)

    factor = pbr.get("baseColorFactor", (1, 1, 1, 1))
    if "under" in override:  # a cut-out over a flat colour
        cut = load(pbr.get("baseColorTexture"), "RGBA", (255, 255, 255, 255))
        under = Image.new("RGB", cut.size, tuple(override["under"]))
        base = Image.composite(cut.convert("RGB"), under, cut.getchannel("A"))
    else:
        base = load(pbr.get("baseColorTexture"), "RGB", (255, 255, 255))
    base = ImageChops.multiply(base, Image.new("RGB", base.size, tuple(round(255 * f) for f in factor[:3])))
    if gain != 1.0:  # base maps made for an engine that brightens them (Halo's multiply with the light)
        base = base.point(lambda v: min(255, round(v * gain)))
    if "color" in override:
        base = Image.new("RGB", (cell, cell), tuple(override["color"]))
    elif "emissiveTexture" in m or any(m.get("emissiveFactor", (0, 0, 0))):
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


def same_maps(gltf, material, overrides):
    """what makes a material's maps: materials alike share their square of the atlas"""
    m = gltf.g["materials"][material] if "materials" in gltf.g else {}
    keep = ("pbrMetallicRoughness", "emissiveTexture", "emissiveFactor", "normalTexture")
    return json.dumps([{k: m.get(k) for k in keep}, overrides.get(m.get("name", "").lower())], sort_keys=True)


def tiles(prims):
    """per material, the whole texture repeats its texture coordinates span: (u from, v from, across, down);
    a hundredth of a repeat over the edge does not count"""
    span = {}
    for p in prims:
        for u, v in p["uv"]:
            lo, hi = span.get(p["material"], ((math.inf, math.inf), (-math.inf, -math.inf)))
            span[p["material"]] = ((min(lo[0], u), min(lo[1], v)), (max(hi[0], u), max(hi[1], v)))
    out = {}
    for mat, (lo, hi) in span.items():
        first = [math.floor(c + 0.01) for c in lo]
        count = [max(1, min(MAX_TILES, math.ceil(h - 0.01) - f)) for h, f in zip(hi, first)]
        out[mat] = (*first, *count)
    return out


def tiled(im, across, down, cell):
    if (across, down) == (1, 1):
        return im
    out = Image.new(im.mode, (im.width * across, im.height * down))
    for i in range(across):
        for j in range(down):
            out.paste(im, (i * im.width, j * im.height))
    return out.resize((cell, cell), Image.LANCZOS)


def atlas(gltf, materials, size, gloss, flip_green, gain=1.0, overrides=None, repeats=None):
    """the diffuse (RGBA) and normal (RGB) atlases and each material's (u0, v0, scale, u from, v from,
    across, down) in it; overrides = {material name (lower case): material_maps override}, repeats = tiles()"""
    overrides = overrides or {}
    repeats = repeats or {}
    squares = {}  # (same_maps key, repeats) -> the materials drawn from it
    for mat in materials:
        squares.setdefault((same_maps(gltf, mat, overrides), repeats.get(mat, (0, 0, 1, 1))), []).append(mat)
    side = math.ceil(math.sqrt(len(squares)))
    cell = size // side
    pad = max(1, PAD * cell // 512)
    diffuse = Image.new("RGBA", (size, size), (0, 0, 0, gloss[0]))
    normal = Image.new("RGB", (size, size), (128, 128, 255))
    place = {}
    lo, hi = gloss
    for k, alike in enumerate(squares.values()):
        mat = alike[0]
        x, y = (k % side) * cell, (k // side) * cell
        override = overrides.get(material_name(gltf, mat).lower())
        base, smooth, nrm = material_maps(gltf, mat, cell, flip_green, gain, override)
        first_u, first_v, across, down = repeats.get(mat, (0, 0, 1, 1))
        base, smooth, nrm = (tiled(im, across, down, cell) for im in (base, smooth, nrm))
        alpha = smooth.point(lambda v: round(lo + (hi - lo) * v / 255))
        rgba = Image.merge("RGBA", (*base.split(), alpha))
        inner = cell - 2 * pad
        # the whole square first (its edges stand in for the padding), then the texture inset by pad
        diffuse.paste(rgba, (x, y))
        normal.paste(nrm, (x, y))
        diffuse.paste(rgba.resize((inner, inner), Image.LANCZOS), (x + pad, y + pad))
        normal.paste(nrm.resize((inner, inner), Image.LANCZOS), (x + pad, y + pad))
        for m in alike:
            place[m] = ((x + pad) / size, (y + pad) / size, inner / size, first_u, first_v, across, down)
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


PER_MODEL = (
    "source",
    "axes",
    "rotate",
    "scale",
    "anchor",
    "drop",
    "parts",
    "keep",
    "frame",
    "position_scale",
    "drop_materials",
    "double_sided",
    "template",
    "out",
)


def build(cfg, base):
    models = cfg.get("models") or [{"model": cfg["model"]}]
    sources, atlases = {}, {}
    for mc in models:
        mcfg = {**cfg, **{k: mc[k] for k in PER_MODEL if k in mc}}
        tex = {**cfg.get("texture", {}), **mc.get("texture", {})}
        if tex.get("normal_y", "up") not in ("up", "down"):
            raise SystemExit('error: texture.normal_y is "up" (the glTF standard) or "down" (DirectX style)')
        skey = (
            mcfg["source"],
            tuple(mcfg["axes"]),
            tuple(mcfg.get("drop_materials", ())),
            tuple(mcfg.get("double_sided", ())),
        )
        if skey not in sources:
            sources[skey] = source(mcfg, base)
        gltf, prims = sources[skey][:2]
        overrides = {k.lower(): v for k, v in cfg.get("materials", {}).items()}
        key = (
            skey,
            tex.get("size", 1024),
            tuple(tex.get("gloss", (120, 225))),
            tex.get("normal_y", "up"),
            tex.get("gain", 1.0),
        )
        if key not in atlases:
            materials = sorted({p["material"] for p in prims})
            atlases[key] = atlas(gltf, materials, key[1], key[2], key[3] == "up", key[4], overrides, tiles(prims))
        build_model(mcfg, mc["model"], base, *sources[skey][1:], atlases[key])


def placeholder(verts, tris):
    """one tiny triangle at the bone, out of sight"""
    for q in ((0, 0, 0), (PLACEHOLDER, 0, 0), (0, 0, PLACEHOLDER)):
        verts.append({"pos": q, "uv": (0.5, 0.5), "normal": (0, -1, 0), "tangent": (1, 0, 0), "binormal": (0, 0, 1)})
    tris.append((len(verts) - 3, len(verts) - 2, len(verts) - 1))


def position_scale(setting, meshes):
    """None (the template's), a number, or "fit": the finest power-of-two multiple of 1/32767 that holds
    every vertex"""
    if setting != "fit":
        return setting
    top = max((abs(c) for verts, _ in meshes for v in verts for c in v["pos"]), default=0.0)
    k = 1
    while top * 32767 / k > 32767:
        k *= 2
    return k / 32767


def build_model(cfg, name, base, prims, piece, boxes, fr, maps):
    """one model of the config: the template's .xbg with the glTF on its bones, and its textures"""
    diffuse, normal, place = maps
    folder = base / cfg["template"]
    template = (folder / name).read_bytes()
    model = xbg.Model(template)
    names = [b.name.lower() for b in model.bones]
    for bone in [*cfg.get("parts", {}), *([cfg["frame"]] if "frame" in cfg else [])]:
        if bone.lower() not in names:
            print(f"  note: {name} has no bone {bone!r}; its pieces stay on the frame")

    # the weapon's material (its largest submesh's): each bone's geometry goes into its submesh with it
    def maps_of(sm):
        m = model.materials[sm.material] if sm.material < len(model.materials) else None
        return (m.diffuse, m.bump) if m else (None, None)

    def size(sm):
        return len(xbg.strip_triangles(sm.strip))

    largest = max(model.submeshes, key=size)
    material = maps_of(largest)
    frame = names.index(cfg["frame"].lower()) if cfg.get("frame", "").lower() in names else model.part_of(largest).bone
    target = {}  # bone -> the submesh its geometry goes into
    for sm in model.submeshes:
        bone = model.part_of(sm).bone
        if maps_of(sm) == material and (bone not in target or size(sm) > size(model.submeshes[target[bone]])):
            target[bone] = sm.index

    keep = {names.index(b.lower()) for b in cfg.get("keep", ()) if b.lower() in names}
    drop = cfg.get("drop", [])
    parts = [(names.index(b.lower()), entries) for b, entries in cfg.get("parts", {}).items() if b.lower() in names]
    owner = {}  # (primitive, piece) -> bone, None when left out

    def owner_of(k, n):
        if (k, n) not in owner:
            lo, hi, _ = boxes[n]
            bone = None if any(selects(e, prims[k], lo, hi) for e in drop) else frame
            for b, entries in parts:
                if bone is not None and any(selects(e, prims[k], lo, hi) for e in entries):
                    bone = b
            if bone is not None and bone not in target:
                raise SystemExit(f"error: {name}: bone {model.bones[bone].name} has no submesh with the weapon's maps")
            owner[(k, n)] = bone
        return owner[(k, n)]

    scale = cfg["scale"]
    src, dst = cfg["anchor"]["source"], cfg["anchor"]["target"]
    turn = rotation(cfg.get("rotate", (0, 0, 0)))  # about the anchor

    # each submesh: its vertices (in its bone's frame) and triangles
    meshes = {sm.index: ([], []) for sm in model.submeshes}
    frame_of = {bone: model.bone_matrix(bone) for bone in target}
    dropped = 0
    for k, (p, ids, f) in enumerate(zip(prims, piece, fr)):
        u0, v0, s, fu, fv, nu, nv = place[p["material"]]
        remap = {}
        for tri, n in zip(p["tris"], ids):
            bone = owner_of(k, n)
            if bone is None:
                dropped += 1
                continue
            verts, tris = meshes[target[bone]]
            rot, pos = frame_of[bone]
            back = transpose(rot)
            dirs = xbg.mat_mul(back, turn)
            out = []
            for i in tri:
                if (bone, i) not in remap:
                    world = xbg.add(dst, xbg.mat_vec(turn, tuple((c - s) * scale for c, s in zip(p["pos"][i], src))))
                    u, v = p["uv"][i]
                    verts.append(
                        {
                            "pos": xbg.mat_vec(back, sub(world, pos)),
                            "uv": (
                                u0 + min(max((u - fu) / nu, 0.0), 1.0) * s,
                                v0 + min(max((v - fv) / nv, 0.0), 1.0) * s,
                            ),
                            "normal": xbg.mat_vec(dirs, p["normal"][i]),
                            "tangent": xbg.mat_vec(dirs, f[i][0]),
                            "binormal": xbg.mat_vec(dirs, f[i][1]),
                        }
                    )
                    remap[(bone, i)] = len(verts) - 1
                out.append(remap[(bone, i)])
            a, b, c = out
            tris.append((a, c, b))  # the games' front faces turn the other way
    for sm in model.submeshes:
        verts, tris = meshes[sm.index]
        if model.part_of(sm).bone in keep:
            if tris:
                raise SystemExit(f"error: {name}: pieces on {model.bones[model.part_of(sm).bone].name}, a kept bone")
            if maps_of(sm) == material:
                raise SystemExit(f"error: {name}: {model.bones[model.part_of(sm).bone].name} has the weapon's maps")
            verts += sm.vertices
            tris += xbg.strip_triangles(sm.strip)
        elif not tris:  # a bone without a piece, a submesh with other maps
            placeholder(verts, tris)
    ordered = [meshes[sm.index] for sm in model.submeshes]
    rebuilt = xbg.rebuild(template, ordered, position_scale(cfg.get("position_scale"), ordered))

    outs = [base / o for o in (cfg["out"] if isinstance(cfg["out"], list) else [cfg["out"]])]
    for out in outs:
        target_file = out / name
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(rebuilt)
    paths = [t.lstrip("\\").replace("\\", "/").lower() for t in model.textures]
    if material == (None, None):  # no maps named: every texture, a normal map by its name
        written = [(path, path.endswith("_nt.xbt")) for path in paths]
    else:
        written = [(paths[t], t == material[1]) for t in material if t is not None]
    for path, is_normal in written:
        old = folder / path
        fmt = DXT1 if is_normal or (old.exists() and xbt.header(old.read_bytes())[3] == DXT1) else DXT5
        data = dxt_xbt(normal if is_normal else diffuse, fmt)
        for out in outs:
            f = out / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
    new = xbg.Model(rebuilt)
    kept = sorted(set(paths) - {path for path, _ in written})
    print(f"{name}: {dropped} triangles left out, position scale {new.scale:.6g}")
    if kept:
        print(f"  textures kept as they are: {', '.join(kept)}")
    for sm in new.submeshes:
        print(
            f"  {model.bones[new.part_of(sm).bone].name}: {len(sm.vertices)} vertices, "
            f"{len(xbg.strip_triangles(sm.strip))} triangles, strip of {len(sm.strip)}"
        )


def transpose(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def info(cfg, base):
    _, prims, piece, boxes, _ = source(cfg, base)
    lo = [min(b[0][k] for b in boxes.values()) for k in range(3)]
    hi = [max(b[1][k] for b in boxes.values()) for k in range(3)]
    digits = max(1, 3 - math.floor(math.log10(max(max(b - a for a, b in zip(lo, hi)), 1e-9))))
    nodes = {}
    for p, ids in zip(prims, piece):
        for n in ids:
            nodes.setdefault(n, set()).add(p["node"])
    print(f"box {fmt3(lo, digits)} .. {fmt3(hi, digits)} (axes turned, glTF units)")
    for n, (lo, hi, count) in sorted(boxes.items(), key=lambda kv: -kv[1][2]):
        print(
            f"  piece {n:3d}: {count:6d} triangles, {fmt3(lo, digits)} .. {fmt3(hi, digits)}"
            f"  {', '.join(sorted(nodes[n]))}"
        )


def fmt3(v, digits=1):
    return "(" + ", ".join(f"{c:.{digits}f}" for c in v) + ")"


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
