"""Put a glTF vehicle (a Halo CE vehicle export) in place of one of the games' vehicles: the vehicle's .xbg
with the new geometry on its bones (body, wheels, steering wheel, turret), its wrecks and debris, the atlas
and a flat normal map in the textures they use, laid out as a mod folder for the game's mod loader
(re/notes/VEHICLES.md; README, "Mods").

  python -B tools/vehicle_import.py <config.json>          the mod folder
  python -B tools/vehicle_import.py info <config.json>     the source's nodes, the wheels and the fit

The bones, the physics in the model's tail and the scripts stay the template's: the wheels' physics
cylinders, the hull boxes, the seats and the gun's helpers do not move; only what is drawn changes.

The config (paths relative to it):

  {
    "game": "../../FarCryEvolution/game",                read only: the templates come from its archives
    "archives": ["levels/*", "farcryed"],                 where to write, of the archives (paths without
                                                          .dat) that hold a model (default: all of them)
    "out": "../../mods/evolution/halo-warthog-humvee",    the mod folder: <out>/<archive>/<path>, mod.ini
    "mod": {"name": "...", "group": "Halo: vehicles", "description": "...", "credit": "..."},
    "source": "../export/vehicles/warthog/warthog.gltf",
    "axes": ["-x", "z", "y"],                             the game's X (right), Y (forward), Z (up) as glTF axes
    "drop_materials": ["warthog_windshield"],             glTF materials left out (default: the BLEND ones)
    "keep_materials": ["warthog_lights"],                 BLEND materials kept anyway (drawn opaque)
    "texture": {"size": 1024, "gain": 1.8, "gloss": [126, 155]},
    "wheels": {"Wheel1": "frame left front tire", ...},   the template's wheel bones and the source's tires
    "body": {"scale": "wheelbase", "width": 0.9, "offset": [0, 0, 0]},
                                                          metres per unit: a number, or "wheelbase" (the
                                                          template's over the source's); "width" narrows
                                                          the body (times the scale across); offset in metres
    "models": [{"model": "objects_xbox/vehicles/hummer/hummer.xbg", "parts": [...], "drop": [...]}, ...]
  }

A model's "parts" say which bone gets which triangles and where, in order (a triangle goes to the first
part that selects it):

    {"bone": "hull2", "rest": true}                       every triangle no other part took (or dropped)
    {"bone": "Wheel1", "wheel": "frame left front tire", "nodes": ["frame left front engine"]}
                                                          the tire's centre on the template's wheel centre
                                                          (its bone's geometry), scaled to its radius;
                                                          "nodes" move along (hubs)
    {"bone": "turret_mesh", "nodes": ["frame gun mount base"], "anchor": {"source": [..], "target": [..]},
     "scale": 2.3, "rotate": [0, 0, 0]}                    source point (units, axes turned) to target (metres,
                                                          the bone's frame), "rotate" in degrees about X, Y, Z
    {"bone": "HUMMER_WRECKED_HOOD", "boxes": [[[..], [..]]], "centre": true}
                                                          triangles whose middle lies in a box; centre: the
                                                          selection's middle on the bone, at the body scale
    "color": [70, 66, 60, 255]                             the vertex colour (materials whose vertices have one),
    "color": "template"                                   or the colour of the template's nearest vertex (a
                                                          wreck's burn marks in its alpha)
    "offset": [0, 0, -0.1]                                metres added to the body fit (a wreck sits lower)
    "double_sided": true                                  the triangles get a back (debris seen from all sides)
    "inner": {"offset": 0.01, "up": 1.2}                  an inside: each triangle again, turned round, "offset"
                                                          metres in along its normals, its normals turned in and
                                                          tipped up by "up" (lit by the sky); the games draw
                                                          both sides, a shell seen from inside comes out black

A model's "clear": {"around": ["eye_pos", "passenger1_eye_pos"], "radius": 0.3, "bones": ["hull2"]} leaves out
the triangles of those bones that come within the radius of those helper bones (bind pose): the seats' eyes
keep a clear view (the games draw back faces too: a panel next to a camera fills the screen dark); "orbit": 0.28
clears round the level circle of that radius about each eye too, where the camera goes as the head turns (the
games put it 0.27 to 0.28 m before the eye bone in the view's direction, measured). What the cut leaves floating
goes too: a small connected piece (up to 50 triangles) it cuts into goes whole, a larger one keeps only its
largest connected remainder (a windshield frame cut at its pillars loses its top bar).

"lower": {"around": ["eye_pos"], "below": 0.55, "reach": 0.45, "outboard": 0.1, "bones": ["hull2"]} brings
those bones' vertices beside a seat (outboard of its eye, within "reach" along the vehicle) down to "below"
under the eye: the seat looks over the side wall.

Without "wheels" there is no body fit and every part needs "anchor" and "scale" (a gun).

A part selects by "nodes" (glTF node names), "boxes" (source units, axes turned) and/or "pieces"
([{"piece_at": [x, y, z]}]: the connected piece with the vertex nearest that point, such as a gun's armour
plates); with none of them and without "rest" it selects nothing. Without "wheel" or "anchor" a part is
placed by the body fit: the middle of the source's tires on the middle of the template's wheels, at the body
scale, "offset" added. "drop" (nodes, boxes or {"piece_at": ...}, the same way) leaves triangles out of the
model.

All of a model's geometry goes into one material, the template's largest submesh's (or "material": n): each
bone's largest submesh takes its triangles, and is pointed at that material when it has another one of the
same shader (the wheels' own texture stays as it is, other models use it); the other submeshes get a tiny
triangle; "keep_submeshes": [0, 1] keeps those submeshes' own geometry (a model that holds a vehicle and a
gun in one bone, where only the gun is replaced). The materials of the source go into one atlas (each at its
own size, a texture that repeats tiled as often as its triangles need), written in place of that material's
diffuse texture in the template's format; its bump texture gets a flat normal map (Halo CE's shaders have
none). Every model of a config draws from the same atlas, so wrecks and debris that share the vehicle's
texture are rebuilt from the source too. A model's own "texture" settings (a lower "gain" for a first-person
gun) make an atlas of the same layout with them; "diffuse": "<path>" points its material at another of its
textures (one only it and the config's other models use), which then takes that atlas.

"helpers": {"Corona_HeadLight1": "marker headlights", "front_light": [0.9, 0.2, 0.6]} moves helper bones
(lights, exhaust: children of the root) to a glTF node's place or a source point, through the body fit.

Archives: each model goes into every archive (matching "archives") that holds it and one of the config's
"vehicles" (default: its first model; wrecks and debris lie in levels without the vehicle too); archives that
hold different files under the model's name get each rebuilt by itself. A texture goes into every archive
that gets a model drawn with it and holds the texture, else into the archives that hold it; "keep_textures"
(file names) are never written (a flat normal map shared with other models). A mod folder lists what it wrote
in .files; a rebuild removes the files of that list it no longer writes.
"""

import argparse
import fnmatch
import json
import math
from pathlib import Path
import struct
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import character_import as ci  # noqa: E402
import dat2  # noqa: E402
import weapon_import as wi  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

DXT1, DXT5 = wi.DXT1, wi.DXT5
MAX_TILES = 4  # repeats of a texture per side in its place in the atlas
EPS = 1e-3
IDENTITY3 = wi.IDENTITY3


# --- the source -------------------------------------------------------------------------------------------


def read_source(cfg, base):
    """(gltf, primitives in the game's axes without the left-out materials, material names)"""
    gltf = wi.Gltf(Path(base, cfg["source"]))
    mats = gltf.g.get("materials", [])
    names = [m.get("name", str(i)) for i, m in enumerate(mats)]
    drop = {n.lower() for n in cfg.get("drop_materials", ())}
    keep = {n.lower() for n in cfg.get("keep_materials", ())}

    def kept(m):
        name = names[m].lower() if m < len(names) else ""
        blend = m < len(mats) and mats[m].get("alphaMode") == "BLEND"
        return name not in drop and (not blend or name in keep)

    prims = [p for p in wi.turned(gltf.primitives(), cfg.get("axes", ["-x", "z", "y"])) if kept(p["material"])]
    return gltf, prims, names


def box_of(points):
    lo = tuple(min(p[k] for p in points) for k in range(3))
    hi = tuple(max(p[k] for p in points) for k in range(3))
    return lo, hi


def middle(lo, hi):
    return tuple((a + b) / 2 for a, b in zip(lo, hi))


def node_points(prims, node):
    pts = [p["pos"][i] for p in prims if p["node"].lower() == node.lower() for t in p["tris"] for i in t]
    if not pts:
        raise SystemExit(f"error: the source has no node {node!r} (with triangles)")
    return pts


def tire(prims, node):
    """a source tire's centre, radius and width (its axle along the game's X)"""
    lo, hi = box_of(node_points(prims, node))
    return middle(lo, hi), max(hi[1] - lo[1], hi[2] - lo[2]) / 2, hi[0] - lo[0]


def node_place(gltf, axes, name):
    """a glTF node's origin in the game's axes (a marker)"""
    found = []

    def walk(i, parent):
        node = gltf.g["nodes"][i]
        m = wi.mat4_mul(parent, wi.node_matrix(node))
        if node.get("name", "").lower() == name.lower():
            found.append((m[0][3], m[1][3], m[2][3]))
        for c in node.get("children", ()):
            walk(c, m)

    for root in gltf.g["scenes"][gltf.g.get("scene", 0)]["nodes"]:
        walk(root, wi.IDENTITY)
    if not found:
        raise SystemExit(f"error: the source has no node {name!r}")
    return xbg.mat_vec(wi.axes_matrix(axes), found[0])


# --- the template -------------------------------------------------------------------------------------------


def bone_index(model, name):
    names = [b.name.lower() for b in model.bones]
    if name.lower() not in names:
        raise SystemExit(f"error: the model has no bone {name!r}")
    return names.index(name.lower())


def bone_submeshes(model, bone):
    return [sm for sm in model.submeshes if model.part_of(sm).bone == bone]


def wheel(model, name):
    """a template wheel's centre in the model (bind pose), radius and width (its axle along its bone's X)"""
    bone = bone_index(model, name)
    pts = [v["pos"] for sm in bone_submeshes(model, bone) for v in sm.vertices]
    if not pts:
        raise SystemExit(f"error: wheel bone {name} has no geometry")
    lo, hi = box_of(pts)
    rot, pos = model.bone_matrix(bone)
    centre = xbg.add(pos, xbg.mat_vec(rot, middle(lo, hi)))
    return centre, max(hi[1] - lo[1], hi[2] - lo[2]) / 2, hi[0] - lo[0]


# --- the fit ------------------------------------------------------------------------------------------------


class Place:
    """p -> target + turn (scale * (p - source)), in the model: scale a number or one per axis (the source's,
    axes turned); tangents scale along, normals against"""

    def __init__(self, source, target, scale, turn=IDENTITY3):
        self.source, self.target, self.turn = tuple(source), tuple(target), turn
        self.scale = scale
        self.axes = tuple(scale) if isinstance(scale, (list, tuple)) else (scale,) * 3

    def point(self, p):
        d = xbg.mat_vec(self.turn, tuple((c - s) * k for c, s, k in zip(p, self.source, self.axes)))
        return xbg.add(self.target, d)

    def direction(self, d):
        return xbg.unit(xbg.mat_vec(self.turn, tuple(c * k for c, k in zip(d, self.axes))))

    def normal(self, n):
        return xbg.unit(xbg.mat_vec(self.turn, tuple(c / k for c, k in zip(n, self.axes))))


def body_fit(cfg, prims, model):
    """the body's Place and a description: the source's tires' middle on the template's wheels' middle; no
    body fit (None) without "wheels" (then every part needs an anchor)"""
    wheels = cfg.get("wheels") or {}
    if not wheels:
        return None, {}, {}, "no body fit (no wheels)"
    if len(wheels) < 2:
        raise SystemExit('error: "wheels" names at least two template wheel bones and their source tires')
    dst = {b: wheel(model, b) for b in wheels}
    src = {b: tire(prims, n) for b, n in wheels.items()}
    d_mid = tuple(sum(w[0][k] for w in dst.values()) / len(dst) for k in range(3))
    s_mid = tuple(sum(t[0][k] for t in src.values()) / len(src) for k in range(3))

    def span(centres, k):
        front = [c[k] for c in centres if c[1] > 0] if k == 1 else [c[k] for c in centres if c[0] > 0]
        back = [c[k] for c in centres if c[1] <= 0] if k == 1 else [c[k] for c in centres if c[0] <= 0]
        return sum(front) / max(1, len(front)) - sum(back) / max(1, len(back)) if front and back else 0.0

    d_rel = [xbg.sub(w[0], d_mid) for w in dst.values()]
    s_rel = [xbg.sub(t[0], s_mid) for t in src.values()]
    base_d, base_s = span(d_rel, 1), span(s_rel, 1)
    track_d, track_s = span(d_rel, 0), span(s_rel, 0)
    body = cfg.get("body", {})
    scale = body.get("scale", "wheelbase")
    if scale == "wheelbase":
        if not base_s:
            raise SystemExit("error: the tires have no wheelbase to scale by")
        scale = base_d / base_s
    target = xbg.add(d_mid, tuple(body.get("offset", (0, 0, 0))))
    width = body.get("width", 1.0)
    text = (
        f"body: {scale:.4f} m per unit{f', {width:g} of it across' if width != 1 else ''}; wheelbase {base_d:.3f} m "
        f"(source {base_s * scale:.3f} m), track {track_d:.3f} m (source {track_s * scale * width:.3f} m)"
    )
    return Place(s_mid, target, (scale * width, scale, scale) if width != 1 else scale), dst, src, text


def turn_of(part):
    return wi.rotation(part.get("rotate", (0, 0, 0)))


def part_place(part, body, dst, src, prims, model, selected):
    """where a part's triangles go (a Place in the model)"""
    if "wheel" in part:
        centre, radius, _ = wheel(model, part["bone"])
        s_centre, s_radius, _ = tire(prims, part["wheel"])
        return Place(s_centre, centre, part.get("scale", radius / s_radius), turn_of(part))
    rot, pos = model.bone_matrix(bone_index(model, part["bone"]))
    if body is None and ("anchor" not in part or "scale" not in part):
        raise SystemExit(f'error: part on {part["bone"]}: without "wheels" a part needs an anchor and a scale')
    scale = part.get("scale", body.scale if body else 1.0)  # a number, or the body's (per axis)
    if "anchor" in part:
        target = xbg.add(pos, xbg.mat_vec(rot, part["anchor"]["target"]))
        return Place(part["anchor"]["source"], target, scale, xbg.mat_mul(rot, turn_of(part)))
    if part.get("centre"):
        if not selected:
            raise SystemExit(f"error: part on {part['bone']} selects no triangle")
        return Place(middle(*box_of(selected)), pos, scale, xbg.mat_mul(rot, turn_of(part)))
    target = xbg.add(body.target, tuple(part.get("offset", (0, 0, 0))))
    return Place(body.source, target, scale, xbg.mat_mul(turn_of(part), body.turn))


class Piece:
    """a selector {"piece_at": [x, y, z]}: the connected piece (over shared positions) with the vertex nearest
    the point (source units, axes turned)"""

    def __init__(self, prims, piece, point):
        near = [
            (math.dist(p["pos"][i], point), ids[t])
            for p, ids in zip(prims, piece)
            for t, tri in enumerate(p["tris"])
            for i in tri
        ]
        self.id = min(near)[1] if near else None


def resolved(entry, prims, piece):
    return Piece(prims, piece, entry["piece_at"]) if isinstance(entry, dict) else entry


def selects(entry, node, centroid, piece=None):
    """a selector: a node name, a box ([lo, hi]) or a Piece"""
    if isinstance(entry, str):
        return node.lower() == entry.lower()
    if isinstance(entry, Piece):
        return piece == entry.id
    lo, hi = entry
    return all(lo[k] <= centroid[k] <= hi[k] for k in range(3))


def part_selects(part, node, centroid, piece=None):
    nodes, boxes, pieces = part.get("nodes"), part.get("boxes"), part.get("pieces")
    if "wheel" in part:
        nodes = [part["wheel"], *(nodes or ())]
    if nodes is None and boxes is None and pieces is None:
        return bool(part.get("rest"))
    return (
        (nodes is None or any(selects(n, node, centroid) for n in nodes))
        and (boxes is None or any(selects(b, node, centroid) for b in boxes))
        and (pieces is None or any(selects(q, node, centroid, piece) for q in pieces))
    )


def assign(mcfg, prims, piece=None):
    """{(primitive, triangle): part number} for the model's parts, the dropped triangles left out"""
    piece = piece or wi.pieces(prims)
    drop = [resolved(e, prims, piece) for e in mcfg.get("drop", [])]
    parts = [
        dict(part, pieces=[resolved(e, prims, piece) for e in part["pieces"]]) if "pieces" in part else part
        for part in mcfg.get("parts", [])
    ]
    owner = {}
    for k, p in enumerate(prims):
        for t, tri in enumerate(p["tris"]):
            c = tuple(sum(p["pos"][i][j] for i in tri) / 3 for j in range(3))
            if any(selects(e, p["node"], c, piece[k][t]) for e in drop):
                continue
            for n, part in enumerate(parts):
                if part_selects(part, p["node"], c, piece[k][t]):
                    owner[(k, t)] = n
                    break
    return owner


# --- the atlas ----------------------------------------------------------------------------------------------


def tile_counts(prims, triangles):
    """per material, the repeats (across, down) of its texture that its triangles need, each triangle moved
    by whole repeats to start in the first"""
    need = {}
    for k, t in triangles:
        p = prims[k]
        uv = [p["uv"][i] for i in p["tris"][t]]
        a, d = need.get(p["material"], (1, 1))
        for axis in (0, 1):
            lo = math.floor(min(c[axis] for c in uv) + EPS)
            span = max(c[axis] for c in uv) - lo
            n = max(1, min(MAX_TILES, math.ceil(span - EPS)))
            a, d = (max(a, n), d) if axis == 0 else (a, max(d, n))
        need[p["material"]] = (a, d)
    return need


def atlas(gltf, need, tex):
    """the RGBA atlas and each material's (u0, v0, du, dv, across, down) in it"""
    materials = sorted(need)
    images = {}
    for m in materials:
        im = ci.material_image(
            gltf, m, tex.get("gain", 1.0), tex.get("gloss", (126, 155)), tex.get("matte", (22, 18, 18))
        )
        across, down = need[m]
        if (across, down) != (1, 1):
            tiled = Image.new("RGBA", (im.width * across, im.height * down))
            for i in range(across):
                for j in range(down):
                    tiled.paste(im, (i * im.width, j * im.height))
            im = tiled
        if "tint" in tex:
            r, g, b, a = im.split()
            r, g, b = (ch.point(lambda v, f=f: min(255, round(v * f / 255))) for ch, f in zip((r, g, b), tex["tint"]))
            im = Image.merge("RGBA", (r, g, b, a))
        images[m] = im
    width, height, _, at, rects = ci.pack([images[m].size for m in materials], tex.get("size", 1024))
    out = Image.new("RGBA", (width, height), (0, 0, 0, tex.get("gloss", (126, 155))[0]))
    place = {}
    for m, (x, y), (w, h) in zip(materials, at, rects):
        im = images[m].resize((w, h), Image.LANCZOS) if (w, h) != images[m].size else images[m]
        out.paste(im.resize((w + 2 * ci.PAD, h + 2 * ci.PAD), Image.BILINEAR), (x, y))
        out.paste(im, (x + ci.PAD, y + ci.PAD))
        place[m] = ((x + ci.PAD) / width, (y + ci.PAD) / height, w / width, h / height, *need[m])
    return out, place


# --- one model ----------------------------------------------------------------------------------------------


def texture_index(model, path):
    paths = [norm(t) for t in model.textures]
    if norm(path) not in paths:
        raise SystemExit(f"error: the model has no texture {path}")
    return paths.index(norm(path))


def main_material(model, mcfg):
    if "material" in mcfg:
        return mcfg["material"]
    largest = max(model.submeshes, key=lambda sm: len(xbg.strip_triangles(sm.strip)))
    return largest.material


def receivers(model, material, bones):
    """{bone: the submesh that takes its triangles}: its largest submesh of the material's shader"""
    shader = model.materials[material].shader
    out = {}
    for bone in bones:
        fits = [sm for sm in bone_submeshes(model, bone) if model.materials[sm.material].shader == shader]
        if not fits:
            raise SystemExit(
                f"error: bone {model.bones[bone].name} has no submesh of material {material}'s shader {shader:08x}"
            )
        out[bone] = max(fits, key=lambda sm: len(sm.vertices)).index
    return out


def convert(template, mcfg, src, body_cfg, place_uv, base):
    """one model: (the rebuilt bytes, the description, {wheel bone: (centre, radius, width)} built)"""
    gltf, prims, frames_of, piece = src
    model = xbg.Model(template)
    body, dst, tires, text = body_fit(body_cfg, prims, xbg.Model(body_cfg["_template"]))
    material = main_material(model, mcfg)
    parts = mcfg.get("parts", [])
    owner = assign(mcfg, prims, piece)
    by_part = {}
    for (k, t), n in owner.items():
        by_part.setdefault(n, []).append((k, t))
    bones = sorted({bone_index(model, parts[n]["bone"]) for n in by_part})
    target = receivers(model, material, bones)
    meshes = {sm.index: ([], []) for sm in model.submeshes}
    frames = {b: model.bone_matrix(b) for b in bones}
    nearest_color = {i: Nearest(model, model.submeshes[i]) for i in set(target.values())}
    lower = mcfg.get("lower", {})  # side walls beside the seats no higher than "below" under the eye
    lower_at = [model.bone_matrix(bone_index(model, b))[1] for b in lower.get("around", ())]
    lower_bones = {bone_index(model, b) for b in lower.get("bones", ())}
    clear = mcfg.get("clear", {})  # room around the seats' eyes: no triangle of these bones comes nearer
    clear_at = orbits(
        [model.bone_matrix(bone_index(model, b))[1] for b in clear.get("around", ())], clear.get("orbit", 0)
    )
    clear_radius = clear.get("radius", 0.3)
    clear_bones = {bone_index(model, b) for b in clear.get("bones", ())}
    cleared = 0
    built = {}
    for n, tris in sorted(by_part.items()):
        part = parts[n]
        bone = bone_index(model, part["bone"])
        selected = [prims[k]["pos"][i] for k, t in tris for i in prims[k]["tris"][t]]
        place = part_place(part, body, dst, tires, prims, model, selected)
        if bone in clear_bones and clear_at:
            kept = cleared_room(tris, prims, piece, place, clear_at, clear_radius)
            cleared += len(tris) - len(kept)
            tris = kept
        rot, pos = frames[bone]
        back = xbg.transpose(rot)
        verts, out = meshes[target[bone]]
        remap = {}
        for k, t in tris:
            p, f = prims[k], frames_of[k]
            u0, v0, du, dv, across, down = place_uv[p["material"]]
            tri = p["tris"][t]
            fu = math.floor(min(p["uv"][i][0] for i in tri) + EPS)
            fv = math.floor(min(p["uv"][i][1] for i in tri) + EPS)
            idx = []
            for i in tri:
                key = (k, i, fu, fv)
                if key not in remap:
                    u, v = p["uv"][i]
                    world = place.point(p["pos"][i])
                    if bone in lower_bones:
                        world = lowered(world, lower_at, lower)
                    vert = {
                        "pos": xbg.mat_vec(back, xbg.sub(world, pos)),
                        "uv": (
                            u0 + min(max((u - fu) / across, 0.0), 1.0) * du,
                            v0 + min(max((v - fv) / down, 0.0), 1.0) * dv,
                        ),
                        "normal": xbg.mat_vec(back, place.normal(p["normal"][i])),
                        "tangent": xbg.mat_vec(back, place.direction(f[i][0])),
                        "binormal": xbg.mat_vec(back, place.direction(f[i][1])),
                    }
                    if part.get("color") == "template":
                        vert["color"] = nearest_color[target[bone]](world)
                    elif "color" in part:
                        vert["color"] = tuple(part["color"])
                    verts.append(vert)
                    remap[key] = len(verts) - 1
                idx.append(remap[key])
            a, b, c = idx
            out.append((a, c, b))  # the games' front faces turn the other way
            if "inner" in part:  # an inside, a little in from the outside and lit from above
                inner = part["inner"]
                lift, offset = inner.get("up", 1.2), inner.get("offset", 0.01)
                inside = []
                for i in (a, b, c):
                    v = dict(verts[i])
                    n = v["normal"]
                    v["pos"] = tuple(q - offset * m for q, m in zip(v["pos"], n))
                    v["normal"] = xbg.unit(xbg.add(tuple(-x for x in n), xbg.mat_vec(back, (0.0, 0.0, lift))))
                    verts.append(v)
                    inside.append(len(verts) - 1)
                out.append(tuple(inside))  # (a, b, c): the other way round from (a, c, b)
            if part.get("double_sided"):  # the games draw one side: a back with the normals turned
                back_idx = []
                for i in (a, b, c):
                    v = dict(verts[i])
                    for f in ("normal", "tangent", "binormal"):
                        v[f] = tuple(-x for x in v[f])
                    verts.append(v)
                    back_idx.append(len(verts) - 1)
                out.append(tuple(back_idx))
        if "wheel" in part:
            pts = [place.point(v) for v in node_points(prims, part["wheel"])]
            lo, hi = box_of(pts)
            built[part["bone"]] = (middle(lo, hi), max(hi[1] - lo[1], hi[2] - lo[2]) / 2, hi[0] - lo[0])
    keep = set(mcfg.get("keep_submeshes", ()))
    for sm in model.submeshes:
        if sm.index in keep:
            if meshes[sm.index][1]:
                raise SystemExit(f"error: submesh {sm.index} is kept but takes triangles")
            meshes[sm.index][0].extend(sm.vertices)
            meshes[sm.index][1].extend(xbg.strip_triangles(sm.strip))
        elif not meshes[sm.index][1]:
            wi.placeholder(*meshes[sm.index])
    ordered = [meshes[sm.index] for sm in model.submeshes]
    scale = None
    top = max(abs(c) for verts, _ in ordered for v in verts for c in v["pos"])
    if top / model.scale > 32767:
        scale = wi.position_scale("fit", ordered)
    rebuilt = bytearray(xbg.rebuild(template, ordered, scale))
    for sm_index in target.values():  # the receiving submeshes draw with the main material
        sm = model.submeshes[sm_index]
        if sm.material != material:
            word = struct.unpack_from("<I", rebuilt, sm.at)[0]
            struct.pack_into("<I", rebuilt, sm.at, (word & 0xFFFF0000) | material)
    if "diffuse" in mcfg:  # the material draws from another of the model's textures (its own gain)
        struct.pack_into("<i", rebuilt, model.materials[material].at + 0x0C, texture_index(model, mcfg["diffuse"]))
    moved = move_helpers(rebuilt, model, mcfg.get("helpers", {}), body, gltf, body_cfg)
    new = xbg.Model(bytes(rebuilt))
    counts = ", ".join(
        f"{model.bones[b].name} {len(xbg.strip_triangles(new.submeshes[target[b]].strip))}" for b in bones
    )
    text = (
        f"{len(owner) - cleared} triangles ({counts}); position scale {new.scale:.6g}"
        + (f"; {cleared} cleared round {len(clear_at)} camera points" if clear_at else "")
        + (f"; helpers moved: {', '.join(moved)}" if moved else "")
    )
    return bytes(rebuilt), text, built


def orbits(eyes, radius, steps=16):
    """each eye and, with a radius, points on the level circle round it: where a seat's camera goes as the head
    turns (in the games it sits 0.27 to 0.28 m before the eye bone in the view's direction)"""
    out = []
    for e in eyes:
        out.append(tuple(e))
        if radius:
            for k in range(steps):
                a = 2 * math.pi * k / steps
                out.append((e[0] + radius * math.cos(a), e[1] + radius * math.sin(a), e[2]))
    return out


def lowered(p, seats, lower):
    """a point beside a seat (outboard of its eye by "outboard", within "reach" along the vehicle) brought
    down to "below" under the eye, so that the seat looks over the wall"""
    below, reach, outboard = lower.get("below", 0.55), lower.get("reach", 0.45), lower.get("outboard", 0.1)
    x, y, z = p
    for e in seats:
        side = 1.0 if e[0] >= 0 else -1.0
        if abs(y - e[1]) < reach and side * (x - e[0]) > outboard and z > e[2] - below:
            z = e[2] - below
    return (x, y, z)


SMALL_PIECE = 50  # triangles: a piece this small goes whole when the room around a seat cuts into it


def cleared_room(tris, prims, piece, place, around, radius):
    """the triangles left when those within radius of the points (placed) go, and what that cut off: a small
    piece goes whole, a large one keeps its largest connected remainder (no floating remnants)"""
    cut = {
        (k, t)
        for k, t in tris
        if any(
            point_triangle(c, *(place.point(prims[k]["pos"][i]) for i in prims[k]["tris"][t])) < radius for c in around
        )
    }
    if not cut:
        return tris
    size = {}
    for k, t in tris:
        size[piece[k][t]] = size.get(piece[k][t], 0) + 1
    touched = {piece[k][t] for k, t in cut}
    keep = [
        (k, t)
        for k, t in tris
        if (k, t) not in cut and not (piece[k][t] in touched and size[piece[k][t]] <= SMALL_PIECE)
    ]
    # the rest of each large touched piece: its largest connected remainder
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def corner(k, i):
        return tuple(round(c, 3) for c in prims[k]["pos"][i])

    rest = [(k, t) for k, t in keep if piece[k][t] in touched]
    for k, t in rest:
        a = find(corner(k, prims[k]["tris"][t][0]))
        for i in prims[k]["tris"][t][1:]:
            b = find(corner(k, i))
            if a != b:
                parent[b] = a
    groups = {}
    for k, t in rest:
        groups.setdefault((piece[k][t], find(corner(k, prims[k]["tris"][t][0]))), []).append((k, t))
    largest = {}
    for (pc, _root), members in groups.items():
        if len(members) > len(largest.get(pc, ())):
            largest[pc] = members
    stay = {kt for members in largest.values() for kt in members}
    return [(k, t) for k, t in keep if piece[k][t] not in touched or (k, t) in stay]


def point_triangle(p, a, b, c):
    """the distance from point p to triangle abc"""
    ab, ac, ap = xbg.sub(b, a), xbg.sub(c, a), xbg.sub(p, a)
    d1, d2 = wi.dot(ab, ap), wi.dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return math.dist(p, a)
    bp = xbg.sub(p, b)
    d3, d4 = wi.dot(ab, bp), wi.dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return math.dist(p, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return math.dist(p, xbg.add(a, tuple(v * x for x in ab)))
    cp = xbg.sub(p, c)
    d5, d6 = wi.dot(ab, cp), wi.dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return math.dist(p, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return math.dist(p, xbg.add(a, tuple(w * x for x in ac)))
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return math.dist(p, xbg.add(b, tuple(w * x for x in xbg.sub(c, b))))
    total = va + vb + vc
    v, w = vb / total, vc / total
    return math.dist(p, xbg.add(a, tuple(v * x + w * y for x, y in zip(ab, ac))))


class Nearest:
    """the colour of a submesh's vertex nearest a point in the model (bind pose): a wreck's burn marks"""

    CELL = 0.25

    def __init__(self, model, sm):
        self.grid = {}
        for v in model.placed(sm):
            key = tuple(math.floor(c / self.CELL) for c in v["pos"])
            self.grid.setdefault(key, []).append((v["pos"], v.get("color", (255, 255, 255, 255))))

    def __call__(self, p):
        key = tuple(math.floor(c / self.CELL) for c in p)
        for reach in range(1, 12):
            near = [
                e
                for dx in range(-reach, reach + 1)
                for dy in range(-reach, reach + 1)
                for dz in range(-reach, reach + 1)
                for e in self.grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ())
            ]
            if near:
                return min(near, key=lambda e: math.dist(e[0], p))[1]
        return (255, 255, 255, 255)


def move_helpers(b, model, helpers, body, gltf, cfg):
    """helper bones (children of the root) moved to a source node's place or point through the body fit"""
    done = []
    at = struct.unpack_from("<I", b, xbg.H_BONES)[0] + 4
    for name, where in helpers.items():
        bone = bone_index(model, name)
        if model.bones[bone].parent != model.root:
            raise SystemExit(f"error: helper {name} is not a child of the root")
        src = node_place(gltf, cfg.get("axes", ["-x", "z", "y"]), where) if isinstance(where, str) else where
        p = body.point(src)
        rot, pos = model.bone_matrix(model.root)
        local = xbg.mat_vec(xbg.transpose(rot), xbg.sub(p, pos))
        struct.pack_into("<3f", b, at + bone * xbg.BONE + 0x1C, *local)
        done.append(name)
    return done


# --- the files ------------------------------------------------------------------------------------------------


class Archives:
    """the game's archives, read only: which hold a file, and the files"""

    def __init__(self, game):
        self.game = Path(game)
        self.index, self.cache = {}, {}
        for fat in sorted(list(self.game.glob("*.fat")) + list(self.game.glob("levels/*/*.fat"))):
            rel = fat.relative_to(self.game).with_suffix("").as_posix()
            if "sound" not in rel.lower():
                self.index[rel] = {e[2] for e in dat2.index(fat.read_bytes())}

    def holders(self, path, patterns=()):
        h = dat2.name_hash(path)
        return [rel for rel, hashes in self.index.items() if h in hashes and matches(rel, patterns)]

    def read(self, rel, path):
        if rel not in self.cache:
            self.cache[rel] = dat2.read(self.game / rel)
        return self.cache[rel].get(dat2.name_hash(path))


def matches(rel, patterns):
    return not patterns or any(fnmatch.fnmatch(rel.lower(), p.lower()) for p in patterns)


def norm(p):
    return ci.norm_path(p)


def frames_for(prims):
    stats = [0, 0]
    return [wi.frames(p, stats) for p in prims]


def build(cfg, base, only_info=False):
    arch = Archives(Path(base, cfg["game"]))
    patterns = cfg.get("archives", ())
    gltf, prims, names = read_source(cfg, base)
    anchors = [norm(v) for v in cfg.get("vehicles", [cfg["models"][0]["model"]] if cfg.get("models") else [])]
    allowed = {rel for v in anchors for rel in arch.holders(v, patterns)}
    models = []
    for mc in cfg.get("models", []):
        path = norm(mc["model"])
        held = [rel for rel in arch.holders(path, patterns) if rel in allowed]
        if not held:
            print(
                f"note: no archive that holds a vehicle of the config {'and that it names ' if patterns else ''}"
                f"holds {path}: left out"
            )
            continue
        variants = {}  # archives may hold different models under one name: each is rebuilt by itself
        for rel in held:
            variants.setdefault(arch.read(rel, path), []).append(rel)
        if len(variants) > 1:
            print(
                f"note: {path} comes in {len(variants)} versions: "
                + "; ".join(", ".join(r.split("/")[-1] for r in rels) for rels in variants.values())
            )
        for template, rels in variants.items():
            models.append({"cfg": mc, "path": path, "archives": rels, "template": template})
    if not models:
        raise SystemExit("error: the config names no model")
    body_cfg = dict(cfg, _template=models[0]["template"])
    body, dst, src, text = body_fit(body_cfg, prims, xbg.Model(models[0]["template"]))
    print(f"{cfg['source']}: {sum(len(p['tris']) for p in prims)} triangles; {text}")
    for b, (c, r, w) in dst.items():
        s = src[b]
        print(
            f"  {b}: template centre {wi.fmt3(c, 3)} radius {r:.3f} width {w:.3f}; source {cfg['wheels'][b]} "
            f"radius {s[1]:.3f} width {s[2]:.3f} units"
        )
    if only_info:
        info(prims, names)
        return
    piece = wi.pieces(prims)
    owners = {id(m): assign(m["cfg"], prims, piece) for m in models}
    need = tile_counts(prims, [key for o in owners.values() for key in o])
    images = {}  # texture settings -> atlas; one layout for all (the same materials at the same sizes)

    def atlas_for(mc):
        tex = {**cfg.get("texture", {}), **mc.get("texture", {})}
        key = json.dumps(tex, sort_keys=True)
        if key not in images:
            images[key] = atlas(gltf, need, tex)
            im = images[key][0]
            print(f"atlas {im.width}x{im.height} {key}: {', '.join(names[m] for m in sorted(need))}")
        return key

    place_uv = images[atlas_for({})][1]
    frames = frames_for(prims)
    out = Path(base, cfg["out"])
    written, textures = [], {}
    for m in models:
        model = xbg.Model(m["template"])
        src_set = (gltf, prims, frames, piece)
        rebuilt, text, built = convert(m["template"], m["cfg"], src_set, body_cfg, place_uv, base)
        print(f"{m['path']}: {text}")
        for b, (c, r, w) in built.items():
            want = wheel(model, b)
            print(
                f"  {b}: centre {wi.fmt3(c, 3)} ({1000 * math.dist(c, want[0]):.1f} mm from the template's), "
                f"radius {r:.3f} (template {want[1]:.3f}), width {w:.3f} (template {want[2]:.3f})"
            )
        mat = xbg.Model(rebuilt).materials[main_material(model, m["cfg"])]
        key = atlas_for(m["cfg"])
        tex = [(norm(model.textures[mat.diffuse]), key)] if mat.diffuse is not None else []
        tex += [(norm(model.textures[mat.bump]), None)] if mat.bump is not None else []
        for rel in m["archives"]:
            written.append(ci.write(out / rel / m["path"], rebuilt))
            for path, what in tex:
                if textures.setdefault(path, (what, set()))[0] != what:
                    raise SystemExit(f"error: models want {path} with different texture settings")
                textures[path][1].add(rel)
        print(f"  -> {len(m['archives'])} archives: {', '.join(a.split('/')[-1] for a in m['archives'])}")
    flat = Image.new("RGB", (ci.FLAT_NORMAL, ci.FLAT_NORMAL), (128, 128, 255))
    keep = {norm(t).split("/")[-1] for t in cfg.get("keep_textures", ())}
    for path, (what, rels) in sorted(textures.items()):
        bump = what is None
        if path.split("/")[-1] in keep:
            continue
        where = [rel for rel in sorted(rels) if arch.read(rel, path) is not None] or arch.holders(path)
        if not where:
            raise SystemExit(f"error: no archive holds {path}")
        old = arch.read(where[0], path)
        fmt = DXT1 if bump or xbt.header(old)[3] == DXT1 else DXT5
        data = wi.dxt_xbt(flat if bump else images[what][0], fmt)
        for rel in where:
            written.append(ci.write(out / rel / path, data))
        print(f"{path}: {'flat normal map' if bump else 'atlas'} -> {len(where)} archives")
    if cfg.get("mod"):
        out.mkdir(parents=True, exist_ok=True)
        ci.write_mod_ini(out, cfg["mod"])
    ci.tidy(out, written)


def info(prims, names):
    nodes = {}
    for p in prims:
        pts = [p["pos"][i] for t in p["tris"] for i in t]
        lo, hi = box_of(pts)
        key = (p["node"], names[p["material"]] if p["material"] < len(names) else str(p["material"]))
        old = nodes.get(key)
        if old:
            lo = tuple(map(min, lo, old[0]))
            hi = tuple(map(max, hi, old[1]))
        nodes[key] = (lo, hi, (old[2] if old else 0) + len(p["tris"]))
    for (node, mat), (lo, hi, n) in sorted(nodes.items()):
        print(f"  {node:30s} {mat:24s} {n:5d} triangles  {wi.fmt3(lo, 3)} .. {wi.fmt3(hi, 3)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("args", nargs="+", metavar="[info] config")
    a = ap.parse_args()
    info_only = a.args[0] == "info" and len(a.args) == 2
    path = Path(a.args[1] if info_only else a.args[0])
    cfg = json.loads(path.read_text(encoding="utf-8"))
    build(cfg, path.parent, only_info=info_only)


if __name__ == "__main__":
    main()
