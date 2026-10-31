"""Put a skinned glTF character (a Halo CE biped export) in place of one of the games' characters: its
skeleton mapped onto the character's 3ds Max Biped bones, its mesh conformed to the character's bind pose
and skinned to those bones, its materials in one texture; the files laid out as a mod folder for the
game's mod loader (re/notes/CHARACTERS.md, "Importing a character"; README, "Mods").

  python -B tools/character_import.py <config.json> [mod ...]       the mod folders (all, or those named)
  python -B tools/character_import.py info <config.json> [mod ...]  the joints, the mapping and the fit per bone

The config (paths relative to it):

  {
    "game": "../FarCryEvolution/game",                    read only: the templates come from its archives
    "archives": ["levels/[0-9]*"],                         where to write: of the level archives holding the
                                                           model those these patterns match (default: all)
    "template": "extract",                                 instead of game: a folder of extracted files
    "out": "mods/evolution/halo-elite-pirates",            the mod folder: <out>/<archive>/<path>, mod.ini
    "mod": {"name": "...", "group": "Halo", "description": "...", "credit": "..."},
    "axes": ["x", "-z", "y"],                              the game's X (left), Y (back), Z (up) as glTF axes
    "scale": 3.048,                                        metres per glTF unit
    "fit": {"thickness": 0.8, "size": {"Bip01_Head": 0.9}, "offset": {"Bip01_Head": [0, 0.02, 0.07]},
            "keep": ["Bip01_Head"], "ground": ["Bip01_L Foot", "Bip01_R Foot"],
            "split": {"Bip01_L Forearm": ["Bip01_L Forearm RollBone"]}},  (keep, ground, split: these defaults)
    "bones": {"bip01 neck1": null, "frame mandible lower left": "Bip01_Jaw"},
    "joints": [{"name": "l fist", "parent": "bip01 l forearm", "at": 0.42, "bone": "Bip01_L Hand"}],
                                                           new joints: the parent's vertices past "at" metres
    "reshape": [{"joint": "bip01 spine1", "material": "grunt_head_and_back", "pivot": [0, 0.1, 0.9],
                 "axis": [1, 0, 0], "angle": 35}],        source parts turned before the fit (game axes, metres)
    "drop": ["elite_inset_lights"],                        glTF materials left out (default: the transparent ones)
    "texture": {"size": 1024, "gain": 1.6, "gloss": [126, 155], "matte": [22, 18, 18],
                "diffuse": ".../vest_df.xbt", "bump": ".../poches_df.xbt"},  (the files that take the atlas and
                                                           the flat normal map; default the material's own)
    "hide": ["animations/characters/hats/beret01.xbg"],    models made invisible (hats)
    "models": [{"model": "animations/.../pirate_kit_01.xbg", "source": "elite/elite.gltf", "material": 0}]
  }

Several mods from one config: "mods": [{"out": ..., "mod": {...}, "models": [...]}, ...], each entry over the
rest of the config; "creatures": {"grunt": {"source": ..., "fit": {...}, ...}} are settings a model takes with
"creature": "grunt" (a model's settings: the config's or its mod's, then its creature's, then its own; nested
objects such as "fit" and "texture" merge). A mod without models hides its "hide" models in the archives that
hold them and "archives" names. Mods that replace different models must not write the same file (the game's
mod menu would switch one off with the other); those that replace the same models are alternatives and do.
Each mod folder lists what it wrote in .files (the game's loader skips dot files); a rebuild removes the files
of that list it no longer writes.

The mapping: a joint goes to the bone of the same name (case, spaces and underscores aside: Character Studio's
"bip01 l upperarm" is the Biped's "Bip01_L UpperArm"), "bones" overrides that (null: no bone). A joint
without a bone moves with its nearest mapped ancestor and gives it its weights (a Halo elite's horselinks,
neck1 and mandibles).

The fit, per mapped joint: where its joint goes (its bone's origin, plus "offset" in metres) and how the
points around it follow, so that every vertex is the blend of its joints' maps (as a pose would move it).
A joint whose mapped child lies along its x axis (the Biped's bones point along x) on a descendant of its
bone is "aligned": its child goes to the child's bone (the length between them fits; what hangs past
either end keeps its size), its hinge axis (z) onto the bone's, thickness "thickness" (times the scale).
Other joints carry their frame onto their bone's ("frame": hands, feet, pelvis) or keep the source's
orientation ("keep": the head looks ahead whatever the neck did), at "size" (default the thickness).
"ground" bones move up or down until their lowest vertex stands on the template's floor (the aligned
parent stretches to meet them). Bones of the template between a joint's bone and its child's (Spine2
between Spine1 and Neck) and its "split" bones (roll bones) share its weights along its length. Each
vertex keeps its two largest weights.

The materials go into one atlas at their own resolution (shelf-packed): base colour times its factor plus
emission, "gain" (with a soft shoulder), "matte" in alpha-masked holes, gloss from 1 - roughness as alpha.
It replaces the diffuse texture of the template's "material" (a 28-byte vertex shader in the characters),
a flat normal map its bump texture; every mesh part (_LOD0, _LOD1) gets the whole mesh, the other skinned
parts (body armour, logo plates) one invisible triangle, "parts": {"NAME": "keep"} keeps one. Texture files
are often shared (a level's dead bodies wear the mercenaries' trousers): "diffuse" and "bump" can name any
other two of the template's textures, ideally ones no other model uses, and the material is pointed at them
(each level's file list names a model's own textures; a new file name might not be loaded).

"joints" adds joints to the source: the vertices of "parent" past "at" metres along its x axis (blended over
"blend", default 0.03) move to the new joint, which goes to "bone": a Grunt's fist, part of its forearm,
goes to the hand bone, so that the forearm fits the template's and the weapon sits in the fist.

"entity_scale": 0.77 (a model's setting) has the game draw every AI that wears the model at that size, its
skeleton, animations, hit capsules and physics with it (BasicAI's own per-entity scale, PropertiesInstance.
fScale, which OnReset hands to SetStatObjScale): the mod ships BasicAI with a hook (lua/scripts/default/
entities/ai/basicai.lua_compiled, the same bytes in every mod of the config that has a scaled model, so they
do not conflict) and the model's carrier: one of the game's AI character scripts (lua_patch.CARRIERS, one per
scaled model of the config, in the order of the models' file names) with one more line, HaloScale[<stem of the
model's file>] = size. The hook loads the carriers once (they are always there: a LoadScript of a missing
script stops the game) and scales an AI whose Properties.fileModel's stem HaloScale names: the size follows
whichever alternative for that model is switched on.

"reshape" turns the vertices whose largest weight is on "joint", whose material is "material" and that lie
in "box" (any of the three may be left out) rigidly about "pivot", before the fit: a part that the fit would
turn with its joint (a Grunt's methane tank tips back with the straightened spine) is turned the other way.
"""

import argparse
import fnmatch
import json
import math
from pathlib import Path
import struct
import sys

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dat2  # noqa: E402
import lua_patch  # noqa: E402
import weapon_import  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

DXT1, DXT5 = weapon_import.DXT1, weapon_import.DXT5
PAD = 4  # texels around each material in the atlas
CHAIN_COS = 0.5  # a mapped child within 60 degrees of a joint's x axis continues its chain
BLEND = 0.35  # weights shared between split bones over this part of the pieces next to each border
FLAT_NORMAL = 64  # side of the flat normal map
# defaults for the games' Biped rigs (a missing bone is skipped)
DEFAULT_FIT = {
    "thickness": 1.0,
    "keep": ["Bip01_Head"],
    "ground": ["Bip01_L Foot", "Bip01_R Foot"],
    "split": {"Bip01_L Forearm": ["Bip01_L Forearm RollBone"], "Bip01_R Forearm": ["Bip01_R Forearm RollBone"]},
}
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


# --- small linear algebra (3x3 as row tuples) ------------------------------------------------------------


mat_mul, mat_vec, transpose, add, sub, unit = xbg.mat_mul, xbg.mat_vec, xbg.transpose, xbg.add, xbg.sub, xbg.unit
cross, dot = weapon_import.cross, weapon_import.dot


def scaled(v, f):
    return tuple(c * f for c in v)


def length(v):
    return math.sqrt(dot(v, v))


def columns(m):
    return [tuple(m[r][c] for r in range(3)) for c in range(3)]


def from_columns(cols):
    return tuple(tuple(cols[c][r] for c in range(3)) for r in range(3))


def outer(a, b):
    return tuple(tuple(a[i] * b[j] for j in range(3)) for i in range(3))


def mat_add(a, b, f=1.0):
    return tuple(tuple(a[i][j] + f * b[i][j] for j in range(3)) for i in range(3))


def mat_scale(a, f):
    return tuple(tuple(a[i][j] * f for j in range(3)) for i in range(3))


def cofactor(m):
    """det(m) times the inverse transpose: what takes normals along with m"""
    c = columns(m)
    return from_columns([cross(c[1], c[2]), cross(c[2], c[0]), cross(c[0], c[1])])


def det(m):
    return dot(columns(m)[0], cross(columns(m)[1], columns(m)[2]))


def basis(primary, secondary):
    """an orthonormal frame (columns): primary, secondary made orthogonal to it, their cross product"""
    p = unit(primary)
    s = sub(secondary, scaled(p, dot(secondary, p)))
    if length(s) < 1e-6:  # secondary along primary: any perpendicular
        s = cross(p, (1.0, 0.0, 0.0) if abs(p[0]) < 0.9 else (0.0, 1.0, 0.0))
    s = unit(s)
    return from_columns([p, s, cross(p, s)])


def align(src_dir, src_hinge, dst_dir, dst_hinge):
    """the rotation taking src_dir onto dst_dir and the hinge axes onto each other as far as they can go"""
    return mat_mul(basis(dst_dir, dst_hinge), transpose(basis(src_dir, src_hinge)))


def angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def rotation(axis, degrees):
    """the rotation by degrees about axis (right-handed)"""
    x, y, z = unit(tuple(axis))
    a = math.radians(degrees)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def merged(*layers):
    """dicts merged in order, nested dicts merged as well (other values replaced)"""
    out = {}
    for layer in layers:
        for k, v in (layer or {}).items():
            out[k] = merged(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


# --- the source: a skinned glTF, in the game's axes and metres ------------------------------------------


class Joint:
    def __init__(self, name, parent, rot, at):
        self.name, self.parent, self.rot, self.at = name, parent, rot, at  # rot: columns = its axes

    @property
    def axes(self):
        return columns(self.rot)


def node_worlds(g):
    """{node: (4x4 world matrix rows, parent node or None)}"""
    out = {}

    def walk(i, parent, m):
        world = weapon_import.mat4_mul(m, weapon_import.node_matrix(g["nodes"][i]))
        out[i] = (world, parent)
        for c in g["nodes"][i].get("children", ()):
            walk(c, i, world)

    for root in g["scenes"][g.get("scene", 0)]["nodes"]:
        walk(root, None, weapon_import.IDENTITY)
    return out


def read_source(path, axes, scale):
    """(joints, primitives, the Gltf) of a skinned glTF placed as its nodes stand (the bind pose of the
    exports): joints in node order with their frames; primitives with pos, normal, uv, tris (counter-
    clockwise from the front, as in glTF), material, skin [(joint, weight)] per vertex"""
    gltf = weapon_import.Gltf(path)
    g = gltf.g
    if not g.get("skins"):
        raise SystemExit(f"error: {path} has no skin: export the skinned model")
    worlds = node_worlds(g)
    a = weapon_import.axes_matrix(axes)
    mirror = det(a) < 0
    joint_nodes = sorted({j for s in g["skins"] for j in s["joints"]})
    number = {n: k for k, n in enumerate(joint_nodes)}
    joints = []
    for n in joint_nodes:
        m, parent = worlds[n]
        while parent is not None and parent not in number:
            parent = worlds[parent][1]
        axes_ = [mat_vec(a, unit((m[0][c], m[1][c], m[2][c]))) for c in range(3)]
        if mirror:  # keep the frame right-handed
            axes_[2] = scaled(axes_[2], -1)
        at = scaled(mat_vec(a, (m[0][3], m[1][3], m[2][3])), scale)
        joints.append(Joint(g["nodes"][n].get("name", f"node{n}"), number.get(parent), from_columns(axes_), at))
    prims = []
    for n in sorted(worlds):
        node = g["nodes"][n]
        if "mesh" not in node:
            continue
        if "skin" not in node:
            raise SystemExit(f"error: mesh node {node.get('name', n)} has no skin")
        skin = g["skins"][node["skin"]]
        ibm = gltf.accessor(skin["inverseBindMatrices"])
        jm = [
            weapon_import.mat4_mul(worlds[j][0], tuple(tuple(ibm[k][c * 4 + r] for c in range(4)) for r in range(4)))
            for k, j in enumerate(skin["joints"])
        ]
        for p in g["meshes"][node["mesh"]]["primitives"]:
            if p.get("mode", 4) != 4:
                continue
            at = p["attributes"]
            if "JOINTS_0" not in at or "WEIGHTS_0" not in at:
                raise SystemExit(f"error: a primitive of {node.get('name', n)} has no JOINTS_0 / WEIGHTS_0")
            pos, nrm = gltf.accessor(at["POSITION"]), gltf.accessor(at["NORMAL"])
            ids, wts = gltf.accessor(at["JOINTS_0"]), gltf.accessor(at["WEIGHTS_0"])
            out = {"pos": [], "normal": [], "skin": []}
            for v, nv, slots, ws in zip(pos, nrm, ids, wts):
                total = sum(ws) or 1.0
                wp, wn, merged = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), {}
                for k, w in zip(slots, ws):  # k: the slot in the skin's joint list
                    if w <= 0:
                        continue
                    w /= total
                    wp = add(wp, scaled(weapon_import.mat4_point(jm[k], v), w))
                    wn = add(wn, scaled(weapon_import.mat4_dir(jm[k], nv), w))
                    joint = number[skin["joints"][k]]
                    merged[joint] = merged.get(joint, 0.0) + w
                out["pos"].append(scaled(mat_vec(a, wp), scale))
                out["normal"].append(unit(mat_vec(a, wn)))
                out["skin"].append(sorted(merged.items(), key=lambda jw: -jw[1]))
            idx = [v[0] for v in gltf.accessor(p["indices"])]
            tris = [tuple(idx[k : k + 3]) for k in range(0, len(idx) - 2, 3)]
            out["tris"] = [(x, z, y) for x, y, z in tris] if mirror else tris
            out["uv"] = [v[:2] for v in gltf.accessor(at["TEXCOORD_0"])]
            out["material"] = p.get("material", 0)
            out["node"] = node.get("name", str(n))
            prims.append(out)
    return joints, prims, gltf


def reshape(joints, prims, gltf, rules):
    """turn parts of the source rigidly before the fit: per rule the vertices whose largest weight is on
    "joint", whose material is "material" and that lie in "box" ([low corner, high corner]; any of the three
    may be missing) about "pivot" by "angle" degrees about "axis" (game axes, metres)"""
    names = [m.get("name", str(i)) for i, m in enumerate(gltf.g.get("materials", []))]
    for rule in rules:
        rot, pivot = rotation(rule["axis"], rule["angle"]), tuple(rule["pivot"])
        joint = key(rule["joint"]) if "joint" in rule else None
        lo, hi = rule.get("box", ((-1e9,) * 3, (1e9,) * 3))
        moved = 0
        for p in prims:
            if "material" in rule and names[p["material"]] != rule["material"]:
                continue
            for i, skin in enumerate(p["skin"]):
                if joint is not None and key(joints[skin[0][0]].name) != joint:
                    continue
                if not all(a <= c <= b for a, c, b in zip(lo, p["pos"][i], hi)):
                    continue
                p["pos"][i] = add(pivot, mat_vec(rot, sub(p["pos"][i], pivot)))
                p["normal"][i] = mat_vec(rot, p["normal"][i])
                moved += 1
        if not moved:
            raise SystemExit(f"error: reshape {rule}: no vertex has that joint and material in that box")


def add_joints(joints, prims, rules):
    """new joints that take the far end of a joint's vertices (a Grunt's fist off its forearm): per rule
    "name", "parent" (a joint), "at" (metres along the parent's x axis), "blend" (metres either side of the
    cut over which the weights pass on, default 0.03), "bone" (where it goes); returns {name: bone}"""
    bones = {}
    for rule in rules:
        parent = next((j for j, joint in enumerate(joints) if key(joint.name) == key(rule["parent"])), None)
        if parent is None:
            raise SystemExit(f"error: joints: the glTF has no joint {rule['parent']}")
        pj, cut, blend = joints[parent], rule["at"], rule.get("blend", 0.03)
        new = len(joints)
        joints.append(Joint(rule["name"], parent, pj.rot, add(pj.at, scaled(pj.axes[0], cut))))
        moved = 0
        for p in prims:
            for i, (pos, skin) in enumerate(zip(p["pos"], p["skin"])):
                w = dict(skin).get(parent, 0.0)
                if w <= 0:
                    continue
                s = dot(sub(pos, pj.at), pj.axes[0]) - cut
                t = min(1.0, max(0.0, (s + blend) / (2 * blend))) if blend > 0 else float(s >= 0)
                if t <= 0:
                    continue
                moved += 1
                rest = [(j, v) for j, v in skin if j != parent]
                rest += [(j, v) for j, v in ((parent, w * (1 - t)), (new, w * t)) if v > 1e-6]
                p["skin"][i] = sorted(rest, key=lambda jw: -jw[1])
        if not moved:
            raise SystemExit(f"error: joints: no vertex of {rule['parent']} lies past {cut} m")
        bones[rule["name"]] = rule.get("bone")
    return bones


# --- the mapping ----------------------------------------------------------------------------------------


def key(name):
    """names compared without case, underscores or doubled spaces"""
    return " ".join(name.lower().replace("_", " ").split())


def bone_map(joints, model, overrides=None):
    """{joint: bone} by name, overrides {joint name: bone name or None} first; only bones with a skin matrix"""
    bones = {key(b.name): i for i, b in enumerate(model.bones)}
    over = {key(k): v for k, v in (overrides or {}).items()}
    known = {key(j.name) for j in joints}
    for k in over:
        if k not in known:
            raise SystemExit(f'error: "bones" names {k}, which the glTF has no joint of')
    direct = {}
    for j, joint in enumerate(joints):
        k = key(joint.name)
        target = over[k] if k in over else joint.name if k in bones else None
        if target is None:
            continue
        if key(target) not in bones:
            raise SystemExit(f"error: joint {joint.name} -> {target}: the model has no such bone")
        b = bones[key(target)]
        if model.bones[b].skin < 0:
            if k in over:
                raise SystemExit(f"error: bone {model.bones[b].name} has no skin matrix: vertices cannot use it")
            continue
        direct[j] = b
    if not direct:
        raise SystemExit("error: no joint of the glTF matches a bone of the model")
    return direct


def owners(joints, direct):
    """per joint the mapped joint it moves with: itself, its nearest mapped ancestor, else the nearest
    mapped joint"""
    out = []
    for j in range(len(joints)):
        k = j
        while k is not None and k not in direct:
            k = joints[k].parent
        if k is None:
            k = min(direct, key=lambda m: length(sub(joints[m].at, joints[j].at)))
        out.append(k)
    return out


def descends(model, bone, of):
    """bone lies below of in the model's hierarchy"""
    b = model.bones[bone].parent
    while b >= 0:
        if b == of:
            return True
        b = model.bones[b].parent
    return False


def path_between(model, top, bottom):
    """the bones strictly between top and its descendant bottom, top down"""
    out, b = [], model.bones[bottom].parent
    while b >= 0 and b != top:
        out.append(b)
        b = model.bones[b].parent
    return out[::-1]


# --- the fit --------------------------------------------------------------------------------------------


class Fit:
    """per mapped joint: mode, chain child, target point, linear map; per vertex: its conformed place,
    normal and the bones' weights"""

    def __init__(self, joints, prims, model, direct, cfg=None):
        cfg = dict(DEFAULT_FIT, **(cfg or {}))
        self.joints, self.model, self.direct = joints, model, direct
        self.owner = owners(joints, direct)
        names = {key(b.name): i for i, b in enumerate(model.bones)}
        pick = lambda lst: {names[key(n)] for n in lst if key(n) in names}  # noqa: E731
        keep, ground = pick(cfg.get("keep", ())), pick(cfg.get("ground", ()))
        size = {names[key(n)]: f for n, f in cfg.get("size", {}).items() if key(n) in names}
        offset = {names[key(n)]: tuple(v) for n, v in cfg.get("offset", {}).items() if key(n) in names}
        split = {names[key(n)]: list(pick(lst)) for n, lst in cfg["split"].items() if key(n) in names}
        thick = cfg.get("thickness", 1.0)
        self.frames = frames = model.frames()
        self.floor = cfg.get("floor", floor_of(model))
        self.chain = {}  # the mapped child each joint reaches for, if any
        for j, b in direct.items():
            best = None
            for c, bc in direct.items():
                parent = joints[c].parent
                if c == j or parent is None or self.owner[parent] != j:
                    continue
                if not descends(model, bc, b):
                    continue
                d = sub(joints[c].at, joints[j].at)
                if length(d) < 1e-6:
                    continue
                cos = dot(d, joints[j].axes[0]) / length(d)
                if cos > CHAIN_COS and (best is None or cos > best[0]):
                    best = (cos, c)
            self.chain[j] = best[1] if best else None
        self.mode = {
            j: "keep" if b in keep else "align" if self.chain[j] is not None else "frame" for j, b in direct.items()
        }
        self.size = {j: size.get(b, thick) for j, b in direct.items()}
        self.linear, self.target = {}, {}
        for j, b in direct.items():
            self.target[j] = add(frames[b][1], offset.get(b, (0.0, 0.0, 0.0)))
            if self.mode[j] == "keep":
                self.linear[j] = mat_scale(IDENTITY, self.size[j])
            elif self.mode[j] == "frame":
                self.linear[j] = mat_scale(mat_mul(frames[b][0], transpose(joints[j].rot)), self.size[j])
        self.ground = {}
        for j, b in direct.items():
            if b in ground and self.mode[j] != "align":
                low = [
                    mat_vec(self.linear[j], sub(p, joints[j].at))[2]
                    for prim in prims
                    for p, skin in zip(prim["pos"], prim["skin"])
                    if self.owner[skin[0][0]] == j
                ]
                if low:
                    dz = self.floor - (self.target[j][2] + min(low))
                    self.target[j] = add(self.target[j], (0.0, 0.0, dz))
                    self.ground[j] = dz
        self.ratio, self.turn, self.splits, self.segment = {}, {}, {}, {}
        for j, b in direct.items():
            if self.mode[j] != "align":  # how far the joint's x axis ends up from the bone's
                self.turn[j] = angle(mat_vec(self.linear[j], joints[j].axes[0]), columns(frames[b][0])[0])
                continue
            c = self.chain[j]
            dh, df = sub(joints[c].at, joints[j].at), sub(self.target[c], self.target[j])
            rot = align(dh, joints[j].axes[2], df, columns(frames[b][0])[2])
            ratio = length(df) / length(dh)
            self.segment[j] = (rot, unit(dh), length(dh), ratio)
            self.ratio[j] = ratio
            self.turn[j] = angle(dh, df)  # how far the limb turns from the source's pose to the template's
            between = [  # once each, and only bones that can take vertices
                s
                for s in dict.fromkeys(path_between(model, b, direct[c]) + split.get(b, []))
                if model.bones[s].skin >= 0
            ]
            if between:
                axis, total = unit(df), length(df)
                cuts = sorted((dot(sub(frames[s][1], self.target[j]), axis) / total, s) for s in between)
                cuts = [(t, s) for t, s in cuts if 0.0 < t < 1.0]
                if cuts:
                    self.splits[j] = (self.target[j], axis, total, cuts)

    def carry(self, joint, pos):
        """where a mapped joint takes a source point, and the linear map it uses there. An aligned joint
        stretches only between itself and its child: what hangs past either end keeps its size (spikes,
        a tentacle, the hip above a thigh)."""
        rel = sub(pos, self.joints[joint].at)
        if joint not in self.segment:
            lin = self.linear[joint]
            return add(self.target[joint], mat_vec(lin, rel)), lin
        rot, u, span, ratio = self.segment[joint]
        size = self.size[joint]
        a = dot(rel, u)
        inside = min(span, max(0.0, a))
        local = add(scaled(sub(rel, scaled(u, a)), size), scaled(u, ratio * inside + size * (a - inside)))
        along = ratio if 0.0 <= a <= span else size
        return add(self.target[joint], mat_vec(rot, local)), mat_mul(
            rot, mat_add(mat_scale(IDENTITY, size), outer(u, u), along - size)
        )

    def place(self, pos, skin):
        """a source vertex's place and the linear map that took it there (its joints' blend)"""
        m, p = ((0.0,) * 3,) * 3, (0.0, 0.0, 0.0)
        for joint, w in skin:
            q, lin = self.carry(self.owner[joint], pos)
            m = mat_add(m, lin, w)
            p = add(p, scaled(q, w))
        return p, m

    def vertex(self, pos, normal, skin):
        """(position, normal, [(bone, weight)] with the two largest weights) in the template's bind pose"""
        p, m = self.place(pos, skin)
        n = unit(mat_vec(cofactor(m), normal)) if det(m) > 0 else normal
        weights = {}
        for joint, w in skin:
            o = self.owner[joint]
            for bone, share in self.shares(o, p):
                weights[bone] = weights.get(bone, 0.0) + w * share
        return p, n, xbg.influences(weights.items())

    def shares(self, joint, p):
        """[(bone, share)] of a vertex at p with weight on joint: its bone, or shared along a split chain"""
        b = self.direct[joint]
        if joint not in self.splits:
            return [(b, 1.0)]
        origin, axis, total, cuts = self.splits[joint]
        t = dot(sub(p, origin), axis) / total
        edges = [0.0] + [c for c, _ in cuts] + [1.0]
        past = [1.0]  # the part of the vertex past each cut
        for k, (c, _) in enumerate(cuts):
            h = BLEND * min(c - edges[k], edges[k + 2] - c)
            past.append(min(1.0, max(0.0, (t - (c - h)) / (2 * h))) if h > 0 else float(t >= c))
        past.append(0.0)
        bones = [b] + [s for _, s in cuts]
        return [(bone, past[k] - past[k + 1]) for k, bone in enumerate(bones) if past[k] - past[k + 1] > 1e-6]

    def table(self):
        """the mapping and the fit, one line per joint"""
        out = []
        for j, joint in enumerate(self.joints):
            if j not in self.direct:
                out.append(f"  {joint.name:28s} -> (with {self.joints[self.owner[j]].name})")
                continue
            b = self.direct[j]
            extra = f"mode {self.mode[j]}, size {self.size[j]:.2f}"
            if self.mode[j] == "align":
                c = self.chain[j]
                extra += f", to {self.joints[c].name}, length x {self.ratio[j]:.2f}, turned {self.turn[j]:.0f} deg"
            else:
                extra += f", x axis {self.turn[j]:.0f} deg off the bone's"
            if j in self.ground:
                extra += f", grounded {self.ground[j]:+.3f} m"
            if j in self.splits:
                extra += ", shares with " + ", ".join(self.model.bones[s].name for _, s in self.splits[j][3])
            out.append(f"  {joint.name:28s} -> {self.model.bones[b].name:26s} {extra}")
        used = set(self.direct.values())
        free = [b.name for i, b in enumerate(self.model.bones) if i not in used and b.skin >= 0]
        out.append("  bones without a joint: " + ", ".join(free))
        return "\n".join(out)


def floor_of(model):
    """the lowest point of the model's mesh parts in the bind pose (its feet's soles)"""
    low = [v["pos"][2] for sm in model.submeshes if sm.skinned for v in model.placed(sm)]
    return min(low) if low else 0.0


# --- textures -------------------------------------------------------------------------------------------


def soft(gain, knee=0.8):
    """a channel lookup table: times gain, rolling off above knee instead of clipping"""
    table = []
    for v in range(256):
        x = v / 255 * gain
        if x > knee:
            x = knee + (1 - knee) * (1 - math.exp(-(x - knee) / (1 - knee)))
        table.append(max(0, min(255, round(x * 255))))
    return table


def material_image(gltf, material, gain=1.0, gloss=(126, 155), matte=(22, 18, 18)):
    """a material as one RGBA image at its base map's size: base colour times its factor plus emission,
    gain, matte in the holes of an alpha-masked map, gloss (from 1 - roughness) as alpha"""
    m = gltf.g["materials"][material] if "materials" in gltf.g else {}
    pbr = m.get("pbrMetallicRoughness", {})
    factor = pbr.get("baseColorFactor", (1, 1, 1, 1))
    if "baseColorTexture" in pbr:
        base = gltf.image(pbr["baseColorTexture"]).convert("RGBA")
    else:
        base = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
    size = base.size
    a = base.getchannel("A").point(lambda v: round(v * factor[3]))
    rgb = ImageChops.multiply(base.convert("RGB"), Image.new("RGB", size, tuple(round(255 * f) for f in factor[:3])))
    if "emissiveTexture" in m or any(m.get("emissiveFactor", (0, 0, 0))):
        if "emissiveTexture" in m:
            glow = gltf.image(m["emissiveTexture"]).convert("RGB").resize(size, Image.LANCZOS)
        else:
            glow = Image.new("RGB", size, (255, 255, 255))
        ef = tuple(round(255 * f) for f in m.get("emissiveFactor", (1, 1, 1)))
        rgb = ImageChops.add(rgb, ImageChops.multiply(glow, Image.new("RGB", size, ef)))
    if gain != 1.0:
        rgb = rgb.point(soft(gain) * 3)
    if m.get("alphaMode") == "MASK":
        cut = round(255 * m.get("alphaCutoff", 0.5))
        holes = a.point(lambda v: 255 if v < cut else 0)
        rgb.paste(Image.new("RGB", size, tuple(matte)), mask=holes)
    mr = pbr.get("metallicRoughnessTexture")
    if mr:
        rough = gltf.image(mr).convert("RGB").getchannel("G").resize(size, Image.LANCZOS)
    else:
        rough = Image.new("L", size, round(255 * pbr.get("roughnessFactor", 1.0)))
    lo, hi = gloss
    alpha = rough.point(lambda v: round(lo + (hi - lo) * (255 - v) / 255))
    return Image.merge("RGBA", (*rgb.split(), alpha))


def shelves(sizes, f, width):
    """shelf packing of the (w, h) rectangles times f (PAD around each) into width: (height used, [(x, y)],
    the scaled sizes), None when one is wider than width"""
    rects = [(max(1, round(w * f)), max(1, round(h * f))) for w, h in sizes]
    if any(r[0] + 2 * PAD > width for r in rects):
        return None
    order = sorted(range(len(rects)), key=lambda k: (-rects[k][1], -rects[k][0]))
    at, x, y, row = [None] * len(rects), 0, 0, 0
    for k in order:
        w, h = rects[k][0] + 2 * PAD, rects[k][1] + 2 * PAD
        if x + w > width:
            x, y, row = 0, y + row, 0
        at[k] = (x, y)
        x, row = x + w, max(row, h)
    return y + row, at, rects


def pack(sizes, size):
    """(width, height, scale, [(x, y)], scaled sizes): the rectangles at their own size (scale 1) or smaller
    in a texture of size x size, size x size / 2 or a smaller square or half; the smallest of those that
    loses at most 15 % of the best scale"""
    fits = {}
    for width in (size, size // 2, size // 4):
        for height in (width, width // 2):
            lo, hi = 0.0, 1.0
            if (s := shelves(sizes, hi, width)) and s[0] <= height:
                lo = hi
            else:
                for _ in range(20):  # the largest scale that fits, to 1/1000
                    mid = (lo + hi) / 2
                    s = shelves(sizes, mid, width)
                    lo, hi = (mid, hi) if s and s[0] <= height else (lo, mid)
            if lo > 0:
                fits[(width, height)] = lo
    if not fits:
        raise SystemExit("error: the materials do not fit the texture size")
    top = max(fits.values())
    width, height = min((wh for wh, f in fits.items() if f >= 0.85 * top), key=lambda wh: wh[0] * wh[1])
    f = fits[(width, height)]
    _, at, rects = shelves(sizes, f, width)
    return width, height, f, at, rects


def build_atlas(gltf, materials, tex):
    """the RGBA atlas and each material's (u0, v0, du, dv) in it"""
    images = {
        m: material_image(gltf, m, tex.get("gain", 1.0), tex.get("gloss", (126, 155)), tex.get("matte", (22, 18, 18)))
        for m in materials
    }
    width, height, _, at, rects = pack([images[m].size for m in materials], tex.get("size", 1024))
    lo = tex.get("gloss", (126, 155))[0]
    out = Image.new("RGBA", (width, height), (0, 0, 0, lo))
    place = {}
    for m, (x, y), (w, h) in zip(materials, at, rects):
        im = images[m].resize((w, h), Image.LANCZOS) if (w, h) != images[m].size else images[m]
        out.paste(im.resize((w + 2 * PAD, h + 2 * PAD), Image.BILINEAR), (x, y))  # its edges into the padding
        out.paste(im, (x + PAD, y + PAD))
        place[m] = ((x + PAD) / width, (y + PAD) / height, w / width, h / height)
    return out, place


# --- the mesh ---------------------------------------------------------------------------------------------


def conformed_mesh(prims, fit, place, keep):
    """(vertices, triangles in the games' winding) of the materials in keep, conformed and skinned; each
    triangle's texture coordinates shifted by whole tiles into 0..1 (vertices split where needed)"""
    verts, tris, index = [], [], {}
    stats = [0, 0]
    for pi, p in enumerate(prims):
        if p["material"] not in keep:
            continue
        u0, v0, du, dv = place[p["material"]]
        conf = [fit.vertex(pos, n, s) for pos, n, s in zip(p["pos"], p["normal"], p["skin"])]
        local = {"pos": [], "normal": [], "uv": [], "tris": [], "tangent": None}
        ids = []
        for t in p["tris"]:
            uvs = [p["uv"][i] for i in t]
            shift = tuple(math.floor(min(uv[k] for uv in uvs) + 1e-4) for k in range(2))
            out = []
            for i in t:
                k = (pi, i, shift)
                if k not in index:
                    index[k] = len(local["pos"])
                    pos, n, skin = conf[i]
                    u, v = (min(1.0, max(0.0, c - s)) for c, s in zip(p["uv"][i], shift))
                    local["pos"].append(pos)
                    local["normal"].append(n)
                    local["uv"].append((u0 + u * du, v0 + v * dv))
                    ids.append(skin)
                out.append(index[k])
            local["tris"].append(tuple(out))
        if not local["tris"]:
            continue
        base = len(verts)
        for (tg, bn), pos, n, uv, skin in zip(
            weapon_import.frames(local, stats), local["pos"], local["normal"], local["uv"], ids
        ):
            verts.append({"pos": pos, "uv": uv, "normal": n, "tangent": tg, "binormal": bn, "skin": skin})
        tris += [(base + a, base + c, base + b) for a, b, c in local["tris"]]  # the games' winding is the other
    return verts, tris


def hidden(model, part):
    """one invisible triangle (three vertices at one point) for a skinned part: on its first bone"""
    sm = model.submeshes[part.first]
    bone = sm.bones[0]
    at = model.bone_matrix(bone)[1]
    v = {"pos": at, "uv": (0.5, 0.5), "normal": (0, 0, 1), "tangent": (1, 0, 0), "binormal": (0, 1, 0)}
    return [(sm.material, [dict(v, skin=[(bone, 1.0)]) for _ in range(3)], [(0, 1, 2)])]


def invisible_rigid(template):
    """a rigid model (a hat) with one invisible triangle per submesh"""
    m = xbg.Model(template)
    v = {"pos": (0.0, 0.0, 0.0), "uv": (0.5, 0.5), "normal": (0, 0, 1), "tangent": (1, 0, 0), "binormal": (0, 1, 0)}
    return xbg.rebuild(template, [([dict(v) for _ in range(3)], [(0, 1, 2)]) for _ in m.submeshes])


def mesh_parts(model, overrides):
    """per part: "mesh" (LOD 0), "lod1", "hide", "keep" (rigid parts and those overrides keep)"""
    names = [p.name for p in model.parts]
    has_lod = any("LOD0" in n.upper() for n in names)
    first = next((i for i, p in enumerate(model.parts) if p.bone is None), None)
    out = []
    for i, p in enumerate(model.parts):
        if p.name in overrides:
            out.append(overrides[p.name])
        elif p.bone is not None:
            out.append("keep")
        elif "LOD1" in p.name.upper():
            out.append("lod1")
        elif ("LOD0" in p.name.upper()) if has_lod else i == first:
            out.append("mesh")
        else:
            out.append("hide")
    return out


def needed_scale(model, verts):
    """the template's position scale, doubled until the new vertices fit in 16 bits around the root (a
    1/32767 model holds +-1 m: an Elite's crest is higher)"""
    rot, pos = model.bone_matrix(model.root)
    back = transpose(rot)
    reach = max(abs(c) for v in verts for c in mat_vec(back, sub(v["pos"], pos)))
    scale = model.scale
    while reach / scale > 32000:
        scale *= 2
    return scale


def rebuild_character(template, verts, tris, material, overrides=None):
    """the template with verts on its mesh parts (LOD 1 the same), the other skinned parts hidden"""
    model = xbg.Model(template)
    roles = mesh_parts(model, overrides or {})
    if "mesh" not in roles:
        raise SystemExit("error: the template has no mesh part (_LOD0)")
    parts = []
    for part, role in zip(model.parts, roles):
        if role in ("mesh", "lod1"):
            parts.append([(material, verts, tris)])
        elif role == "hide":
            parts.append(hidden(model, part))
        else:
            parts.append(None)
    scale = needed_scale(model, verts)
    return xbg.rebuild_skinned(template, parts, scale=scale if scale > model.scale else None), roles


def texture_slots(model, material, tex):
    """(diffuse, bump) texture numbers that take the atlas and the flat normal map: the material's own, or
    the files tex "diffuse" and "bump" name (any two of the model's textures)"""
    mat = model.materials[material]
    paths = [norm_path(t) for t in model.textures]

    def pick(name, own):
        if name is None:
            return own
        if norm_path(name) not in paths:
            raise SystemExit(f"error: the model has no texture {name}")
        return paths.index(norm_path(name))

    diffuse, bump = pick(tex.get("diffuse"), mat.diffuse), pick(tex.get("bump"), mat.bump)
    if diffuse is None:
        raise SystemExit(f"error: material {material} has no texture")
    if bump is not None and mat.bump is None:
        raise SystemExit(f"error: material {material} has no bump texture to point elsewhere")
    if diffuse == bump:
        raise SystemExit("error: the atlas and the normal map need two texture files")
    return diffuse, bump


def with_textures(model_bytes, material, diffuse, bump):
    """the model with the material's diffuse and bump texture numbers set"""
    b = bytearray(model_bytes)
    at = xbg.Model(model_bytes).materials[material].at
    struct.pack_into("<i", b, at + 0x0C, diffuse)
    if bump is not None:
        struct.pack_into("<i", b, at + 0x14, bump)
    return bytes(b)


def convert(template, mcfg, base, only_info=False):
    """one model: {"fit", "text"} and, unless only_info, "model" (the rebuilt bytes), "atlas", "diffuse" and
    "bump" (the paths of the files they go to)"""
    model = xbg.Model(template)
    source = Path(base, mcfg["source"])
    joints, prims, gltf = read_source(source, mcfg.get("axes", ["x", "-z", "y"]), mcfg.get("scale", 1.0))
    bones = dict(mcfg.get("bones") or {})
    if mcfg.get("joints"):
        bones.update(add_joints(joints, prims, mcfg["joints"]))
    if mcfg.get("reshape"):
        reshape(joints, prims, gltf, mcfg["reshape"])
    direct = bone_map(joints, model, bones)
    fit = Fit(joints, prims, model, direct, mcfg.get("fit"))
    out = {"fit": fit, "text": f"{source.name}, {len(joints)} joints, {len(direct)} mapped"}
    if only_info:
        return out
    tex = mcfg.get("texture", {})
    material = mcfg.get("material", 0)
    diffuse, bump = texture_slots(model, material, tex)
    drop = set(mcfg.get("drop", [])) or None
    names = [m.get("name", str(i)) for i, m in enumerate(gltf.g.get("materials", []))]
    used = sorted({p["material"] for p in prims})
    if drop is None:
        keep = [m for m in used if gltf.g["materials"][m].get("alphaMode") != "BLEND"]
    else:
        keep = [m for m in used if names[m] not in drop]
    atlas, place = build_atlas(gltf, keep, tex)
    verts, tris = conformed_mesh(prims, fit, place, set(keep))
    rebuilt, roles = rebuild_character(template, verts, tris, material, mcfg.get("parts"))
    rebuilt = with_textures(rebuilt, material, diffuse, bump)
    new = xbg.Model(rebuilt)
    out.update(
        model=rebuilt,
        atlas=atlas,
        diffuse=norm_path(model.textures[diffuse]),
        bump=norm_path(model.textures[bump]) if bump is not None else None,
    )
    out["text"] += (
        f"\n  {len(tris)} triangles, {len(verts)} vertices, materials {', '.join(names[m] for m in keep)}; "
        f"parts {', '.join(f'{p.name} {r}' for p, r in zip(model.parts, roles))}; "
        f"{len(new.submeshes)} submeshes, position scale {new.scale:.6g}; texture {atlas.width}x{atlas.height} "
        f"in {out['diffuse'].split('/')[-1]}, flat normals in {(out['bump'] or '-').split('/')[-1]}"
    )
    return out


# --- the files ------------------------------------------------------------------------------------------


def norm_path(p):
    return p.replace("\\", "/").lstrip("/").lower()


class Source:
    """the template files: from the game's archives (read only) or a folder of extracted files"""

    def __init__(self, cfg, base):
        self.game = Path(base, cfg["game"]) if cfg.get("game") else None
        self.folder = Path(base, cfg["template"]) if cfg.get("template") else None
        if not self.game and not self.folder:
            raise SystemExit('error: the config needs "game" (its game folder) or "template" (extracted files)')
        self.cache, self.held = {}, {}

    def archive(self, rel):
        if rel not in self.cache:
            self.cache[rel] = dat2.read(self.game / rel)
        return self.cache[rel]

    def read(self, rel, path):
        """a file of archive rel (or of the template folder), None when missing"""
        if self.game:
            return self.archive(rel).get(dat2.name_hash(path))
        f = self.folder / norm_path(path)
        return f.read_bytes() if f.exists() else None

    def holders(self, path):
        """the level archives that hold path (archive names as the mods folder wants them)"""
        if not self.held:  # the indexes only, once
            for fat in sorted(self.game.glob("levels/*/*.fat")):
                rel = fat.relative_to(self.game).with_suffix("").as_posix()
                self.held[rel] = {e[2] for e in dat2.index(fat.read_bytes())}
        h = dat2.name_hash(path)
        return [rel for rel, hashes in self.held.items() if h in hashes]


def matching(names, patterns):
    return [a for a in names if not patterns or any(fnmatch.fnmatch(a.lower(), p.lower()) for p in patterns)]


def model_config(cfg, mc):
    """a model's settings: the config's (or its mod's), its creature's, its own"""
    creatures = cfg.get("creatures", {})
    name = mc.get("creature")
    if name is not None and name not in creatures:
        raise SystemExit(f'error: no creature "{name}" in "creatures"')
    rest = {k: v for k, v in cfg.items() if k not in ("models", "mods", "creatures")}
    return merged(rest, creatures.get(name), mc)


def mod_configs(cfg):
    """the mods of a config: its "mods" over the rest, or the config itself"""
    if "mods" not in cfg:
        return [cfg]
    rest = {k: v for k, v in cfg.items() if k != "mods"}
    return [merged(rest, m) for m in cfg["mods"]]


def plan(cfg, src):
    """what a mod writes: {"id", "cfg", "models": [{"cfg", "path", "archives", "template", "files"}],
    "hats": {archive: [paths]}, "writes": {(archive, path)}}"""
    models, hats = [], {}
    for mc in cfg.get("models", []):
        mcfg = model_config(cfg, mc)
        path = norm_path(mc["model"])
        archives = mcfg.get("archives", [])
        if src.game:  # the level archives that hold the model, those the patterns name if any
            held = src.holders(path)
            archives = matching(held, archives)
            if not archives:
                raise SystemExit(f"error: no level archive {'that the config names ' if held else ''}holds {path}")
        elif not archives:
            raise SystemExit('error: with "template", "archives" names where the files go')
        template = src.read(archives[0], path)
        if template is None:
            raise SystemExit(f"error: {archives[0]} has no {path}")
        model = xbg.Model(template)
        diffuse, bump = texture_slots(model, mcfg.get("material", 0), mcfg.get("texture", {}))
        files = [path] + [norm_path(model.textures[t]) for t in (diffuse, bump) if t is not None]
        models.append({"cfg": mcfg, "path": path, "archives": archives, "template": template, "files": files})
        for rel in archives:
            have = hats.setdefault(rel, [])
            have += [norm_path(h) for h in mcfg.get("hide", []) if norm_path(h) not in have]
    if not models:  # hats alone: in the archives that hold them
        for h in cfg.get("hide", []):
            where = matching(src.holders(norm_path(h)), cfg.get("archives", [])) if src.game else cfg["archives"]
            for rel in where:
                hats.setdefault(rel, []).append(norm_path(h))
    hats = {rel: [h for h in hs if src.read(rel, h) is not None] for rel, hs in hats.items()}
    writes = {(rel, f) for m in models for rel in m["archives"] for f in m["files"]}
    writes |= {(rel, h) for rel, hs in hats.items() for h in hs}
    out = cfg.get("out")
    return {"id": Path(out).name if out else None, "cfg": cfg, "models": models, "hats": hats, "writes": writes}


def check_conflicts(plans):
    """mods that replace different models must not write the same file"""
    owner = {}
    for p in plans:
        replaced = frozenset(m["path"] for m in p["models"])
        for f in sorted(p["writes"]):
            for other, theirs in owner.get(f, []):
                if theirs != replaced:
                    raise SystemExit(
                        f"error: {other} and {p['id']} both write {f[0]}/{f[1]} but replace different models "
                        "(the game's mod menu would switch one off with the other)"
                    )
            owner.setdefault(f, []).append((p["id"], replaced))


def build(cfg, base, only_info=False, only=None):
    src = Source(cfg, base)
    plans = [plan(m, src) for m in mod_configs(cfg)]
    check_conflicts(plans)
    scaled = sorted({m["path"] for p in plans for m in p["models"] if m["cfg"].get("entity_scale")})
    if scaled and not src.game:
        raise SystemExit('error: "entity_scale" needs "game" (the scripts come from its lua.dat)')
    ids = [p["id"] for p in plans]
    for name in only or ():
        if name not in ids:
            raise SystemExit(f"error: no mod {name} in the config ({', '.join(map(str, ids))})")
    for p in plans:
        if not only or p["id"] in only:
            build_mod(p, base, src, only_info, many=len(plans) > 1, scaled=scaled)


def scale_scripts(src, models, scaled):
    """{path in the lua archive: bytes}: BasicAI hooked for every scaled model of the config (the same file
    in each mod that ships it) and the carrier script of each of this mod's scaled models with its size"""
    chunks = lua_patch.scripts(src.game)
    basicai = chunks.get(lua_patch.name_hash(lua_patch.BASICAI))
    if basicai is None:
        raise SystemExit(f"error: {src.game}/lua.dat has no {lua_patch.BASICAI}")
    out = {lua_patch.BASICAI: lua_patch.entity_scale_hook(basicai, scaled)}
    carriers = lua_patch.scale_carriers(scaled)
    for m in models:
        inner = carriers[lua_patch.stem_of(m["path"])][1]
        carrier = chunks.get(lua_patch.name_hash(inner))
        if carrier is None:
            raise SystemExit(f"error: {src.game}/lua.dat has no {inner}")
        out[inner] = lua_patch.scale_marker(carrier, m["path"], m["cfg"]["entity_scale"])
    return out


def build_mod(p, base, src, only_info=False, many=False, scaled=()):
    cfg = p["cfg"]
    out = Path(base, cfg["out"]) if cfg.get("out") else None
    if many:
        print(f"== {p['id']}")
    written = []
    for m in p["models"]:
        done = convert(m["template"], m["cfg"], base, only_info)
        print(f"{m['path']}: {done['text']}")
        if only_info:
            print(done["fit"].table())
            continue
        if out is None:
            continue
        for rel in m["archives"]:
            have = src.read(rel, m["path"])
            if have is None:
                print(f"  {rel}: no {m['path']}, skipped")
                continue
            if have != m["template"]:
                raise SystemExit(f"error: {rel} holds another {m['path']} than {m['archives'][0]}")
            folder = out / rel
            written.append(write(folder / m["path"], done["model"]))
            old = src.read(rel, done["diffuse"])
            fmt = DXT1 if old is not None and xbt.header(old)[3] == DXT1 else DXT5
            written.append(write(folder / done["diffuse"], weapon_import.dxt_xbt(done["atlas"], fmt)))
            if done["bump"]:
                flat = Image.new("RGB", (FLAT_NORMAL, FLAT_NORMAL), (128, 128, 255))
                written.append(write(folder / done["bump"], weapon_import.dxt_xbt(flat, DXT1)))
            print(f"  -> {folder.relative_to(out).as_posix()}")
    if out is None or only_info:
        return
    for rel, hats in p["hats"].items():
        for h in hats:
            written.append(write(out / rel / h, invisible_rigid(src.read(rel, h))))
    mine = [m for m in p["models"] if m["cfg"].get("entity_scale")]
    if mine:  # the game draws, hits and moves these models' wearers at that size (BasicAI's fScale)
        for inner, data in scale_scripts(src, mine, scaled).items():
            written.append(write(out / "lua" / inner.replace("\\", "/"), data))
        sizes = ", ".join(f"{m['cfg']['entity_scale']:g}" for m in mine)
        print(f"  entity scale {sizes}: lua/{lua_patch.BASICAI}")
    if cfg.get("mod"):
        out.mkdir(parents=True, exist_ok=True)
        write_mod_ini(out, cfg["mod"])
    tidy(out, written)


def tidy(out, written):
    """list what the mod folder holds now in <out>/.files; files the earlier list named that this build did
    not write go, and folders they leave empty"""
    listing = out / ".files"
    now = sorted({w.relative_to(out).as_posix() for w in written})
    before = listing.read_text(encoding="utf-8").split("\n") if listing.exists() else []
    for rel in before:
        f = out / rel
        if rel and rel not in now and f.is_file():
            f.unlink()
            print(f"  removed {rel} (no longer written)")
            d = f.parent
            while d != out and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
    out.mkdir(parents=True, exist_ok=True)
    listing.write_text("".join(f"{rel}\n" for rel in now), encoding="utf-8")


def write_mod_ini(out, mod):
    lines = [f"{k} = {mod[k]}" for k in ("name", "group", "description", "credit") if mod.get(k)]
    (out / "mod.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("args", nargs="+", metavar="[info] config [mod]")
    a = ap.parse_args()
    info = a.args[0] == "info" and len(a.args) > 1
    path, only = Path(a.args[1 if info else 0]), a.args[2 if info else 1 :]
    cfg = json.loads(path.read_text(encoding="utf-8"))
    build(cfg, path.parent, only_info=info, only=only)


if __name__ == "__main__":
    main()
