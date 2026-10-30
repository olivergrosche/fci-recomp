"""The games' models (.xbg in the DAT2 archives): read them, place rigid and skinned vertices, export them
as .obj and rebuild one with new geometry (re/notes/MODELS.md, re/notes/CHARACTERS.md).

  python -B tools/xbg.py info <model.xbg>
  python -B tools/xbg.py obj <model.xbg> [<out.obj>] [--lod <n>]

A model is a header of (offset, count) pairs, then its materials, textures, bones, skin matrices, parts,
the submesh table, one block of vertex and index data and a tail (four zero bytes, or a character's physics
shapes); unused space is CD. A part is a run of submeshes. Rigid parts (weapons, props) hang on a bone, their
vertices in its frame. Skinned parts (characters) give each submesh a palette of up to 8 bones; their
vertices are stored in the root bone's frame in the bind pose, each with up to two (palette slot, weight)
pairs, and the skin matrices take them from there into each bone's frame.

rebuild() keeps everything of a rigid model but the geometry (tools/weapon_import.py uses it);
rebuild_skinned() puts new skinned geometry on a character's skeleton, split into submeshes of at most 8
bones, and keeps the materials, textures, bones, skin matrices and physics.
"""

import argparse
import math
from pathlib import Path
import struct

MAGIC = b"\x09\x01\x01"  # after the version byte: 0 Instincts, 1 Evolution
HEADER = 0xB0
SUBMESH = 0x24
PART = 0x30
BONE = 0x48
MATERIAL = 0x30
MATRIX = 0x40  # a skin matrix: 4x4 floats, row-major, for row vectors (Direct3D)
DATA_ALIGN = 32  # each submesh's vertices (from the data start), the end of a rebuilt rigid model's data
TAIL_GAP = 16  # CD bytes between the data and the tail in the games' own models
SUBMESH_TAG = 0xFFFF
PALETTE = 8  # bones per skinned submesh
NO_BONE = 0xFF  # an unused palette slot
NO_PART_BONE = 0xFFFF  # a skinned part in the part index
INFLUENCES = 2  # (bone, weight) pairs per skinned vertex
# header fields: (offset, count) pairs
H_MATERIALS, H_TEXTURES, H_BONES, H_SKIN, H_PART_INDEX, H_PARTS, H_SUBMESHES = 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40
H_DATA, H_RAGDOLL, H_TAIL, H_STRINGS = 0x48, 0x50, 0x58, 0x68
H_BOX, H_SPHERE, H_SCALE, H_UV = 0x70, 0x88, 0x9C, 0xA0
H_BONE_INDEX = H_PART_INDEX  # the name it had while only weapons were known (one part per bone)
RIGID_STRIDE, PLAIN_STRIDE, SKINNED_STRIDE = 24, 16, 28  # first-person weapons, third-person, characters
RIGID = (RIGID_STRIDE, PLAIN_STRIDE)
# after position (4 int16) and uv (2 int16), and a skinned vertex's weights: the fields, by the bytes left
FIELDS = {
    0: (),
    4: ("normal",),
    8: ("normal", "color"),
    12: ("normal", "tangent", "binormal"),
    16: ("normal", "color", "tangent", "binormal"),
}
DIRECTIONS = ("normal", "tangent", "binormal")


def u32(b, at):
    return struct.unpack_from("<I", b, at)[0]


def align(n, to):
    return -(-n // to) * to


class Bone:
    def __init__(self, b, at, strings):
        self.child, self.sibling, self.parent = struct.unpack_from("<3i", b, at)
        self.rotation = struct.unpack_from("<4f", b, at + 0x0C)  # x, y, z, w
        self.position = struct.unpack_from("<3f", b, at + 0x1C)
        self.scale = struct.unpack_from("<3f", b, at + 0x28)
        self.skin = struct.unpack_from("<i", b, at + 0x34)[0]  # its skin matrix, -1 for none
        self.body = struct.unpack_from("<H", b, at + 0x3C)[0]  # its ragdoll body (H_RAGDOLL), 0xFF for none
        self.name = cstring(b, strings + struct.unpack_from("<H", b, at + 0x3E)[0])
        self.hash = u32(b, at + 0x44)


class Material:
    """0x30 bytes: the shader (its low half is the vertex tag of the submeshes that use it), a colour, the
    diffuse and the bump texture (numbers in the texture list, None for none), flags"""

    def __init__(self, b, at):
        self.at = at
        self.shader, self.color = struct.unpack_from("<2I", b, at)
        diffuse, bump = struct.unpack_from("<i", b, at + 0x0C)[0], struct.unpack_from("<i", b, at + 0x14)[0]
        self.diffuse = diffuse if diffuse >= 0 else None
        self.bump = bump if bump >= 0 else None
        self.flags = u32(b, at + 0x28)


class Part:
    """a run of submeshes with a name: the weapons have one per bone, a character its mesh (LOD 0 and 1) and
    attachments such as body armour; triangles, first submesh, its vertex offset, the count, a bounding
    sphere in the frame its vertices are stored in"""

    def __init__(self, b, at, strings, bone):
        self.at = at
        self.triangles, self.first, self.vertex_offset = struct.unpack_from("<3I", b, at)
        self.count = u32(b, at + 0x10) >> 16
        self.centre = struct.unpack_from("<3f", b, at + 0x14)
        self.radius = struct.unpack_from("<f", b, at + 0x20)[0]
        self.name = cstring(b, strings + u32(b, at + 0x24))
        self.lod = struct.unpack_from("<i", b, at + 0x28)[0]  # 0 and 1 on a character's meshes, else -1 or 0
        self.bone = bone  # the bone a rigid part hangs on; None for a skinned part


class Submesh:
    def __init__(self, b, at, index, data, scale, uv):
        w = struct.unpack_from("<5I", b, at)
        self.at = at
        self.index = index
        self.material = w[0] & 0xFFFF
        self.vertex_offset, self.index_offset = w[1], w[2]
        self.stride, count = w[3] >> 16, w[3] & 0xFFFF
        self.vertex_tag, vertices = w[4] >> 16, w[4] & 0xFFFF
        self.palette = list(b[at + 20 : at + 28])
        self.skinned = any(p != NO_BONE for p in self.palette)
        self.raw = b[data + self.vertex_offset : data + self.vertex_offset + vertices * self.stride]
        self.strip = list(struct.unpack_from(f"<{count}H", b, data + self.index_offset))
        palette = self.palette if self.skinned else None
        self.vertices = [
            decode_vertex(self.raw, i * self.stride, self.stride, scale, uv, palette) for i in range(vertices)
        ]

    @property
    def bones(self):
        return [p for p in self.palette if p != NO_BONE]


def fields(stride, skinned):
    """the fields that follow position, uv and (skinned) the weights in a vertex of stride bytes"""
    rest = stride - 12 - 4 * bool(skinned)
    if rest not in FIELDS:
        raise ValueError(f"no known {'skinned' if skinned else 'rigid'} vertex layout of {stride} bytes")
    return FIELDS[rest]


def decode_vertex(raw, at, stride, scale, uv, palette=None):
    """a vertex as a dict: pos, uv, then normal, color (r, g, b, a), tangent, binormal as the stride has them;
    with the submesh's palette (skinned) also skin, the (bone, weight) pairs with a weight"""
    x, y, z, _, s, t = struct.unpack_from("<4h2h", raw, at)
    v = {"pos": (x * scale, y * scale, z * scale), "uv": (s * uv[1] + uv[0], t * uv[1] + uv[0])}
    at += 12
    if palette is not None:  # weight 0, weight 1, 4 * slot 0, 4 * slot 1
        w0, w1, i0, i1 = raw[at : at + 4]
        v["skin"] = [(palette[i >> 2], w / 255) for w, i in ((w0, i0), (w1, i1)) if w]
        at += 4
    for f in fields(stride, palette is not None):
        v[f] = unpack_color(raw, at) if f == "color" else unpack_dir(raw, at)
        at += 4
    return v


def unpack_dir(raw, at):
    """a unit vector as a D3DCOLOR: bytes z, y, x around 128, then 128"""
    z, y, x = raw[at], raw[at + 1], raw[at + 2]
    return ((x - 128) / 127, (y - 128) / 127, (z - 128) / 127)


def pack_dir(v):
    x, y, z = (max(1, min(255, round(c * 127 + 128))) for c in v)
    return bytes((z, y, x, 128))


def unpack_color(raw, at):
    """a D3DCOLOR (bytes b, g, r, a) as (r, g, b, a)"""
    b, g, r, a = raw[at : at + 4]
    return (r, g, b, a)


def pack_color(c):
    r, g, b, a = c
    return bytes((b, g, r, a))


def cstring(b, at):
    return b[at : b.index(b"\0", at)].decode("latin-1")


class Model:
    def __init__(self, b):
        if len(b) < HEADER or b[1:4] != MAGIC:
            raise ValueError("not an .xbg model")
        self.b = b
        self.version = b[0]
        self.scale = struct.unpack_from("<f", b, H_SCALE)[0]
        self.uv = struct.unpack_from("<2f", b, H_UV)
        strings = u32(b, H_STRINGS)
        at, n = u32(b, H_MATERIALS), u32(b, H_MATERIALS + 4)
        self.materials = [Material(b, at + i * MATERIAL) for i in range(n)]
        at, n = u32(b, H_TEXTURES), u32(b, H_TEXTURES + 4)
        self.textures = [cstring(b, strings + u32(b, at + 8 * i)) for i in range(n)]
        at, n = u32(b, H_BONES), u32(b, H_BONES + 4)
        self.bones = [Bone(b, at + 4 + i * BONE, strings) for i in range(n)]
        at, n = u32(b, H_SKIN), u32(b, H_SKIN + 4)
        self.skin_matrices = [struct.unpack_from("<16f", b, at + i * MATRIX) for i in range(n)]
        at, n = u32(b, H_PART_INDEX), u32(b, H_PART_INDEX + 4)
        index = {}  # part: its bone; the entries are (CRC-32 of the part's name, part, bone or 0xFFFF)
        for i in range(n):
            _, part, bone = struct.unpack_from("<IHH", b, at + 8 * i)
            index[part] = bone
        at, n = u32(b, H_PARTS), u32(b, H_PARTS + 4)
        self.parts = [Part(b, at + i * PART, strings, index.get(i, i)) for i in range(n)]
        self.data = u32(b, H_DATA)
        at = u32(b, H_SUBMESHES)
        self.submeshes = [
            Submesh(b, at + k * SUBMESH, k, self.data, self.scale, self.uv)
            for k in range(sum(p.count for p in self.parts))
        ]
        for p in self.parts:
            if p.bone == NO_PART_BONE or any(sm.skinned for sm in self.submeshes[p.first : p.first + p.count]):
                p.bone = None
        self.root = next((i for i, bone in enumerate(self.bones) if bone.parent < 0), 0)

    @property
    def skinned(self):
        return any(sm.skinned for sm in self.submeshes)

    def bone_matrix(self, i):
        """bone i's frame in the model in the bind pose: (3x3 rotation rows, translation)"""
        return self.frames()[i]

    def frames(self, rotations=None):
        """every bone's frame in the model, (rotation rows, translation); rotations = {bone: (x, y, z, w)}
        replaces those bones' rotations relative to their parents (a pose)"""
        rotations = rotations or {}
        out = []
        for i, bone in enumerate(self.bones):
            r, t = quat_matrix(rotations.get(i, bone.rotation)), bone.position
            if bone.parent < 0:
                out.append((r, t))
            else:  # parents come first in every model
                pr, pt = out[bone.parent]
                out.append((mat_mul(pr, r), add(pt, mat_vec(pr, t))))
        return out

    def skin_matrix(self, bone):
        """bone's skin matrix as (rotation rows, translation) for column vectors: from the root's frame (where
        skinned vertices are stored) to the bone's"""
        m = self.skin_matrices[self.bones[bone].skin]
        return tuple(tuple(m[4 * c + r] for c in range(3)) for r in range(3)), m[12:15]

    def part_of(self, submesh):
        for p in self.parts:
            if p.first <= submesh.index < p.first + p.count:
                return p
        return None

    def frame_of(self, submesh, frames=None):
        """the frame a submesh's vertices are stored in: its part's bone, or the root bone if skinned"""
        frames = frames or self.frames()
        part = self.part_of(submesh)
        return frames[self.root if submesh.skinned or part is None or part.bone is None else part.bone]

    def placed(self, submesh):
        """the submesh's vertices in the model in the bind pose"""
        rot, pos = self.frame_of(submesh)
        return [transform(v, rot, pos) for v in submesh.vertices]

    def posed(self, submesh, frames):
        """the submesh's vertices with the bones at frames (from frames()): rigid ones moved with their bone,
        skinned ones blended from their bones' skin matrices (linear blend skinning)"""
        if not submesh.skinned:
            rot, pos = self.frame_of(submesh, frames)
            return [transform(v, rot, pos) for v in submesh.vertices]
        blend = {}
        for b in submesh.bones:
            fr, ft = frames[b]
            sr, st = self.skin_matrix(b)
            blend[b] = (mat_mul(fr, sr), add(ft, mat_vec(fr, st)))
        out = []
        for v in submesh.vertices:
            rot = tuple(tuple(sum(w * blend[b][0][i][j] for b, w in v["skin"]) for j in range(3)) for i in range(3))
            pos = tuple(sum(w * blend[b][1][i] for b, w in v["skin"]) for i in range(3))
            out.append(transform(v, rot, pos, normalise=True))
        return out


def transform(v, rot, pos, normalise=False):
    out = dict(v, pos=add(pos, mat_vec(rot, v["pos"])))
    for f in DIRECTIONS:
        if f in v:
            d = mat_vec(rot, v[f])
            out[f] = unit(d) if normalise else d
    return out


def quat_matrix(q):
    x, y, z, w = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def transpose(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def strip_triangles(strip):
    """the triangles of a strip (degenerate ones dropped), each in the order of the strip's even ones"""
    out = []
    for i in range(len(strip) - 2):
        a, b, c = strip[i : i + 3]
        if a == b or b == c or a == c:
            continue
        out.append((a, b, c) if i % 2 == 0 else (a, c, b))
    return out


def stripify(triangles):
    """one strip for a list of triangles (vertex indices, in the order strip_triangles gives them back):
    greedy walks over shared edges, the walks joined by degenerate triangles"""
    edges = {}
    for t, (a, b, c) in enumerate(triangles):
        for e in ((a, b), (b, c), (c, a)):
            edges.setdefault(e, []).append(t)
    used = [False] * len(triangles)
    strip = []
    for start in range(len(triangles)):
        if used[start]:
            continue
        used[start] = True
        a, b, c = triangles[start]
        walk = [a, b, c]
        while True:  # the next triangle shares the walk's last edge, in the strip's alternating order
            x, y = walk[-2], walk[-1]
            odd = len(walk) % 2 == 1  # the next index makes an odd triangle: (x, d, y) in strip order
            key = (y, x) if odd else (x, y)
            nxt = None
            for t in edges.get(key, ()):
                if not used[t]:
                    nxt = t
                    break
            if nxt is None:
                break
            used[nxt] = True
            ta = triangles[nxt]
            walk.append(next(v for v in ta if v != x and v != y))
        if strip:
            strip += [strip[-1], walk[0]]
            if len(strip) % 2:  # the walk must start on an even triangle
                strip.append(walk[0])
        strip += walk
    return strip


def obj(model, lod=0):
    """the model as Wavefront .obj text in the bind pose, one group per submesh; parts of a higher LOD than
    lod (a character's LOD 1 mesh) are left out"""
    lines, base = [], 1
    for k, sm in enumerate(model.submeshes):
        part = model.part_of(sm)
        if part and part.lod > lod:
            continue
        name = part.name if part else f"submesh{k}"
        if part and part.bone is not None and part.bone < len(model.bones):
            name = model.bones[part.bone].name
        lines.append(f"g {name}_{k}" if part and part.count > 1 else f"g {name}")
        tex = model.materials[sm.material].diffuse if sm.material < len(model.materials) else None
        if tex is not None:
            lines.append("usemtl " + model.textures[tex].replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0])
        for v in model.placed(sm):
            lines.append("v %.6f %.6f %.6f" % v["pos"])
            lines.append("vt %.6f %.6f" % (v["uv"][0], 1 - v["uv"][1]))
            lines.append("vn %.4f %.4f %.4f" % v.get("normal", (0, 0, 1)))
        for a, b, c in strip_triangles(sm.strip):  # .obj wants counter-clockwise front faces
            a, b, c = a + base, c + base, b + base
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        base += len(sm.vertices)
    return "\n".join(lines) + "\n"


def encode_vertex(v, stride, scale, uv, slots=None):
    """a vertex as decode_vertex gives it, pos in the frame it is stored in; skinned with slots, the
    submesh's {bone: palette slot}; a missing color is white"""
    x, y, z = (int_clamp(c / scale) for c in v["pos"])
    s, t = (uv_step(c, uv) for c in v["uv"])
    out = struct.pack("<4h2h", x, y, z, 1, s, t)
    if slots is not None:
        out += pack_skin(v["skin"], slots)
    for f in fields(stride, slots is not None):
        out += pack_color(v.get("color", (255, 255, 255, 255))) if f == "color" else pack_dir(v[f])
    return out


def influences(skin):
    """the (bone, weight) pairs a vertex keeps: the INFLUENCES largest, adding up to 1"""
    pairs = {}
    for b, w in skin:
        pairs[b] = pairs.get(b, 0) + w
    best = sorted(((w, b) for b, w in pairs.items() if w > 0), reverse=True)[:INFLUENCES]
    if not best:
        raise ValueError("a skinned vertex without a bone")
    total = sum(w for w, _ in best)
    return [(b, w / total) for w, b in best]


def pack_skin(skin, slots):
    """weight 0, weight 1 (bytes adding up to 255), 4 * palette slot 0, 4 * slot 1 (0 when unused)"""
    pairs = influences(skin)
    w0 = round(255 * pairs[0][1])
    if len(pairs) == 1 or w0 == 255:
        return bytes((255, 0, 4 * slots[pairs[0][0]], 0))
    return bytes((w0, 255 - w0, 4 * slots[pairs[0][0]], 4 * slots[pairs[1][0]]))


def int_clamp(f):
    i = round(f)
    if not -32768 <= i <= 32767:
        raise ValueError(f"{f:.1f} does not fit in 16 bits: the model is too large for its position scale")
    return i


def uv_step(c, uv):
    """a texture coordinate as int16: uv[0] + s * uv[1], the model's range (0 up to one step below 1 in
    most models, -1 to 4 in some); its far edge (1.0 in most) goes one step in"""
    i = round((c - uv[0]) / uv[1])
    if i == 32768:
        return 32767
    if not -32768 <= i <= 32767:
        lo, hi = uv[0] - 32768 * uv[1], uv[0] + 32768 * uv[1]
        raise ValueError(f"texture coordinate {c:.4f} is outside the model's range {lo:g} to {hi:g}")
    return i


def bounds(points):
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = max(math.dist(centre, p) for p in points)
    return lo, hi, centre, radius


def write_bounds(b, points):
    lo, hi, centre, radius = bounds(points)
    struct.pack_into("<6f", b, H_BOX, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    struct.pack_into("<4f", b, H_SPHERE, *centre, radius)


def rebuild(template, meshes, scale=None):
    """template's bytes with new geometry: meshes[i] = (vertices, triangles) for submesh i, rigid, its
    vertices in its part's bone frame (dicts as decode_vertex gives them), triangles in strip order;
    scale (model units per step) defaults to the template's"""
    m = Model(template)
    if len(meshes) != len(m.submeshes):
        raise ValueError(f"the model has {len(m.submeshes)} submeshes, not {len(meshes)}")
    if m.skinned:
        raise ValueError("a skinned model: use rebuild_skinned")
    b = bytearray(template)
    scale = scale or m.scale
    struct.pack_into("<f", b, H_SCALE, scale)
    data = bytearray()
    placed, part_points, part_triangles, part_offset = [], {}, {}, {}
    for sm, (vertices, triangles) in zip(m.submeshes, meshes):
        strip = stripify(triangles)
        if len(vertices) > 0xFFFF or len(strip) > 0xFFFF:
            raise ValueError(
                f"{len(vertices)} vertices and {len(strip)} strip indices: a submesh holds at most 65535 of each"
            )
        data += b"\xcd" * (-len(data) % DATA_ALIGN)
        vo = len(data)
        data += b"".join(encode_vertex(v, sm.stride, scale, m.uv) for v in vertices)
        io = len(data)
        data += struct.pack(f"<{len(strip)}H", *strip)
        struct.pack_into("<3I", b, sm.at + 4, vo, io, sm.stride << 16 | len(strip))
        struct.pack_into("<I", b, sm.at + 16, sm.vertex_tag << 16 | len(vertices))
        part = m.part_of(sm)
        rot, pos = m.frame_of(sm)
        local = [v["pos"] for v in vertices]
        part_points.setdefault(part.at, []).extend(local)
        part_triangles[part.at] = part_triangles.get(part.at, 0) + len(strip_triangles(strip))
        part_offset.setdefault(part.at, vo)
        placed += [add(pos, mat_vec(rot, p)) for p in local]
    for part in m.parts:
        if part.at in part_points:
            _, _, centre, radius = bounds(part_points[part.at])
            struct.pack_into("<I", b, part.at, part_triangles[part.at])
            struct.pack_into("<I", b, part.at + 8, part_offset[part.at])
            struct.pack_into("<4f", b, part.at + 0x14, *centre, radius)
    write_bounds(b, placed)
    data += b"\xcd" * (-len(data) % DATA_ALIGN)
    tail = m.data + len(data)
    struct.pack_into("<I", b, H_DATA + 4, len(data))
    struct.pack_into("<I", b, H_TAIL, tail)
    return bytes(b[: m.data]) + bytes(data) + template[u32(template, H_TAIL) :]


def split_by_bones(vertices, triangles, limit=PALETTE):
    """[(bones, triangles)]: the triangles in groups whose vertices use at most limit bones together
    (greedy, triangles with the same bones next to each other)"""
    used = [frozenset(b for b, _ in influences(v["skin"])) for v in vertices]
    tri_bones = [used[a] | used[b] | used[c] for a, b, c in triangles]
    remaining = sorted(range(len(triangles)), key=lambda t: sorted(tri_bones[t]))
    groups = []
    while remaining:
        bones, take, rest = set(), [], []
        for t in remaining:
            joined = bones | tri_bones[t]
            if len(joined) <= limit:
                bones = joined
                take.append(triangles[t])
            else:
                rest.append(t)
        groups.append((sorted(bones), take))
        remaining = rest
    return groups


def vertex_stride(material_stride, v):
    """the stride for a new skinned vertex: the material's in the template, else from the fields it has"""
    if material_stride:
        return material_stride
    frame = "tangent" in v and "binormal" in v
    return 20 + 8 * frame + 4 * ("color" in v)


def rebuild_skinned(template, parts, scale=None):
    """template's bytes with new skinned geometry on its skeleton. parts[i] is for the template's part i:
    None keeps it as it is, else a list of meshes (material, vertices, triangles): vertices as dicts in the
    model in the bind pose (pos, uv, normal, and tangent, binormal, color as the material's vertex size
    wants) with skin = [(bone, weight), ...] (the two largest are kept), triangles (vertex indices) in strip
    order. Each mesh becomes as many submeshes as it needs for at most 8 bones each. The materials, textures,
    bones, skin matrices, part names and physics stay; scale defaults to the template's."""
    m = Model(template)
    if len(parts) != len(m.parts):
        raise ValueError(f"the model has {len(m.parts)} parts, not {len(parts)}")
    can_skin = {i for i, bone in enumerate(m.bones) if 0 <= bone.skin < len(m.skin_matrices)}
    strides = {}
    for sm in m.submeshes:
        if sm.skinned:
            strides.setdefault(sm.material, sm.stride)
    scale = scale or m.scale
    rot, pos = m.bone_matrix(m.root)
    back = transpose(rot)
    # (material, stride, vertex bytes, strip, vertex count, palette) per new submesh, and the parts
    submeshes, records, placed = [], [], []
    for part, meshes in zip(m.parts, parts):
        first = len(submeshes)
        points, triangles = [], 0
        if meshes is None:
            for sm in m.submeshes[part.first : part.first + part.count]:
                raw = sm.raw
                if scale != m.scale:  # the same vertices at the new scale
                    slots = {bone: k for k, bone in enumerate(sm.palette) if bone != NO_BONE} if sm.skinned else None
                    raw = b"".join(encode_vertex(v, sm.stride, scale, m.uv, slots) for v in sm.vertices)
                submeshes.append((sm.material, sm.stride, raw, sm.strip, len(sm.vertices), sm.palette))
                triangles += len(strip_triangles(sm.strip))
                points += [v["pos"] for v in sm.vertices]
                placed += [v["pos"] for v in m.placed(sm)]
            records.append((part, first, len(submeshes) - first, triangles, (part.centre, part.radius)))
            continue
        if part.bone is not None:
            raise ValueError(f"part {part.name} is rigid: keep it (None)")
        if not meshes:
            raise ValueError(f"part {part.name} needs a mesh (or None to keep it)")
        for material, vertices, tris in meshes:
            if not 0 <= material < len(m.materials):
                raise ValueError(f"no material {material}: the model has {len(m.materials)}")
            for v in vertices:
                for b, _ in influences(v["skin"]):
                    if b not in can_skin:
                        name = m.bones[b].name if 0 <= b < len(m.bones) else str(b)
                        raise ValueError(f"bone {name} has no skin matrix: skinned vertices cannot use it")
            stride = vertex_stride(strides.get(material), vertices[0])
            for bones, group in split_by_bones(vertices, tris):
                keep = sorted({i for t in group for i in t})
                new = {old: k for k, old in enumerate(keep)}
                slots = {bone: k for k, bone in enumerate(bones)}
                local = []
                for i in keep:
                    v = vertices[i]
                    lv = dict(v, pos=mat_vec(back, sub(v["pos"], pos)))
                    for f in DIRECTIONS:
                        if f in v:
                            lv[f] = mat_vec(back, v[f])
                    local.append(lv)
                strip = stripify([tuple(new[i] for i in t) for t in group])
                if len(local) > 0xFFFF or len(strip) > 0xFFFF:
                    raise ValueError(f"{len(local)} vertices and {len(strip)} strip indices: too many for a submesh")
                raw = b"".join(encode_vertex(v, stride, scale, m.uv, slots) for v in local)
                palette = bones + [NO_BONE] * (PALETTE - len(bones))
                submeshes.append((material, stride, raw, strip, len(local), palette))
                triangles += len(group)
                points += [v["pos"] for v in local]
                placed += [vertices[i]["pos"] for i in keep]
        _, _, centre, radius = bounds(points)
        records.append((part, first, len(submeshes) - first, triangles, (centre, radius)))
    table_at = u32(template, H_SUBMESHES)
    data_at = align(table_at + SUBMESH * len(submeshes) + 4, 16)
    head = bytearray(template[:table_at]) + b"\xcd" * (data_at - table_at)
    struct.pack_into("<f", head, H_SCALE, scale)
    data, offsets = bytearray(), []
    for k, (material, stride, raw, strip, count, palette) in enumerate(submeshes):
        data += b"\xcd" * (-len(data) % DATA_ALIGN)
        vo = len(data)
        data += raw
        io = len(data)
        data += struct.pack(f"<{len(strip)}H", *strip)
        offsets.append(vo)
        tag = m.materials[material].shader & 0xFFFF
        at = table_at + k * SUBMESH
        struct.pack_into(
            "<5I", head, at, SUBMESH_TAG << 16 | material, vo, io, stride << 16 | len(strip), tag << 16 | count
        )
        head[at + 20 : at + 36] = bytes(palette) + bytes(8)
    data += b"\xcd" * (-len(data) % 16)
    for part, first, count, triangles, (centre, radius) in records:
        vo = offsets[first] if count else 0
        struct.pack_into("<3I", head, part.at, triangles, first, vo)
        struct.pack_into("<I", head, part.at + 0x10, count << 16 | u32(template, part.at + 0x10) & 0xFFFF)
        struct.pack_into("<4f", head, part.at + 0x14, *centre, radius)
    write_bounds(head, placed)
    struct.pack_into("<2I", head, H_DATA, data_at, len(data))
    struct.pack_into("<I", head, H_TAIL, data_at + len(data) + TAIL_GAP)
    return bytes(head) + bytes(data) + b"\xcd" * TAIL_GAP + template[u32(template, H_TAIL) :]


def mesh_of(model, part):
    """a part's geometry as rebuild_skinned takes it: [(material, vertices in the model, triangles)], one
    mesh per material, the submeshes' vertices joined"""
    meshes = {}
    for sm in model.submeshes[part.first : part.first + part.count]:
        vertices, triangles = meshes.setdefault(sm.material, ([], []))
        base = len(vertices)
        vertices += model.placed(sm)
        triangles += [(a + base, b + base, c + base) for a, b, c in strip_triangles(sm.strip)]
    return [(material, vertices, triangles) for material, (vertices, triangles) in meshes.items()]


def info(model):
    out = [f"version {model.version}, position scale {model.scale:.6g}, uv {model.uv[0]:g} + s * {model.uv[1]:.6g}"]
    out += [f"texture {i} {t}" for i, t in enumerate(model.textures)]
    for i, mat in enumerate(model.materials):
        out.append(f"material {i}: shader {mat.shader:08x}, diffuse {mat.diffuse}, bump {mat.bump}")
    frames = model.frames()
    for i, bone in enumerate(model.bones):
        out.append(
            f"bone {i} {bone.name}: parent {bone.parent}, skin {bone.skin}, "
            f"at {tuple(round(c, 4) for c in frames[i][1])} in the model, "
            f"rotation {tuple(round(c, 4) for c in bone.rotation)}"
        )
    for i, p in enumerate(model.parts):
        hangs = "skinned" if p.bone is None else f"on {model.bones[p.bone].name}" if p.bone < len(model.bones) else ""
        runs = f"submeshes {p.first}-{p.first + p.count - 1}" if p.count else "no submeshes"
        out.append(f"part {i} {p.name}: lod {p.lod}, {runs}, {p.triangles} triangles, {hangs}")
    for i, sm in enumerate(model.submeshes):
        bones = ", bones " + " ".join(model.bones[b].name for b in sm.bones) if sm.skinned else ""
        out.append(
            f"submesh {i}: material {sm.material}, {len(sm.vertices)} vertices of {sm.stride} bytes, "
            f"{len(strip_triangles(sm.strip))} triangles{bones}"
        )
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("info", "obj"))
    ap.add_argument("model")
    ap.add_argument("target", nargs="?")
    ap.add_argument("--lod", type=int, default=0, help="obj: the highest LOD to export (default 0)")
    a = ap.parse_args()
    src = Path(a.model)
    try:
        model = Model(src.read_bytes())
    except ValueError as e:
        raise SystemExit(f"error: {src}: {e}")
    if a.command == "info":
        print(info(model))
        return
    dst = Path(a.target) if a.target else src.with_suffix(".obj")
    dst.write_text(obj(model, a.lod))
    print(dst)


if __name__ == "__main__":
    main()
