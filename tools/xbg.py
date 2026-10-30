"""The games' models (.xbg in the DAT2 archives): read them, export them as .obj and rebuild one with new
geometry (re/notes/MODELS.md).

  python -B tools/xbg.py info <model.xbg>
  python -B tools/xbg.py obj <model.xbg> [<out.obj>]

A model is a header of (offset, count) pairs, then its materials, textures, bones, parts, the submesh table,
one block of vertex and index data and four zero bytes; unused space is CD. Rigid models (the weapons) hang
each part on a bone, its vertices in the bone's frame: 24 bytes with a tangent frame for the normal map
(first person), 16 with only a normal (third person). Skinned ones (the characters, 28 bytes) are read but
their vertices are not placed yet.

rebuild() keeps everything of a model but the geometry: the same materials, textures, bones and parts,
each part's submesh with new vertices and triangles. tools/weapon_import.py uses it.
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
DATA_ALIGN = 32  # each submesh's vertices, and the end of the data
SUBMESH_TAG = 0xFFFF
# header fields: (offset, count) pairs
H_MATERIALS, H_TEXTURES, H_BONES, H_BONE_INDEX, H_PARTS, H_SUBMESHES, H_DATA, H_TAIL, H_STRINGS = (
    0x10,
    0x18,
    0x20,
    0x30,
    0x38,
    0x40,
    0x48,
    0x58,
    0x68,
)
H_BOX, H_SPHERE, H_SCALE, H_UV = 0x70, 0x88, 0x9C, 0xA0
RIGID_STRIDE, PLAIN_STRIDE, SKINNED_STRIDE = 24, 16, 28  # vertex sizes
RIGID = (RIGID_STRIDE, PLAIN_STRIDE)


def u32(b, at):
    return struct.unpack_from("<I", b, at)[0]


class Bone:
    def __init__(self, b, at, strings):
        self.child, self.sibling, self.parent = struct.unpack_from("<3i", b, at)
        self.rotation = struct.unpack_from("<4f", b, at + 0x0C)  # x, y, z, w
        self.position = struct.unpack_from("<3f", b, at + 0x1C)
        self.scale = struct.unpack_from("<3f", b, at + 0x28)
        self.name = cstring(b, strings + struct.unpack_from("<H", b, at + 0x3E)[0])


class Part:
    """one per bone in the weapons: the bone's submesh, its triangle count and bounding sphere"""

    def __init__(self, b, at):
        self.at = at
        self.triangles, self.bone, self.vertex_offset = struct.unpack_from("<3I", b, at)
        self.centre = struct.unpack_from("<3f", b, at + 0x14)
        self.radius = struct.unpack_from("<f", b, at + 0x20)[0]


class Submesh:
    def __init__(self, b, at, data, scale, uv):
        w = struct.unpack_from("<5I", b, at)
        self.at = at
        self.material = w[0] & 0xFFFF
        self.vertex_offset, self.index_offset = w[1], w[2]
        self.stride, count = w[3] >> 16, w[3] & 0xFFFF
        self.vertex_tag, vertices = w[4] >> 16, w[4] & 0xFFFF
        self.palette = b[at + 20 : at + 28]
        self.raw = b[data + self.vertex_offset : data + self.vertex_offset + vertices * self.stride]
        self.strip = list(struct.unpack_from(f"<{count}H", b, data + self.index_offset))
        self.vertices = [decode_vertex(self.raw, i * self.stride, self.stride, scale, uv) for i in range(vertices)]


def decode_vertex(raw, at, stride, scale, uv):
    x, y, z, _, s, t = struct.unpack_from("<4h2h", raw, at)
    v = {"pos": (x * scale, y * scale, z * scale), "uv": (s * uv[1] + uv[0], t * uv[1] + uv[0])}
    if stride == PLAIN_STRIDE:
        v["normal"] = unpack_dir(raw, at + 12)
        return v
    frame = at + 12 if stride == RIGID_STRIDE else at + 16  # skinned: weights and palette slots first
    v["normal"], v["tangent"], v["binormal"] = (unpack_dir(raw, frame + 4 * k) for k in range(3))
    return v


def unpack_dir(raw, at):
    """a unit vector as a D3DCOLOR: bytes z, y, x around 128, then 128"""
    z, y, x = raw[at], raw[at + 1], raw[at + 2]
    return ((x - 128) / 127, (y - 128) / 127, (z - 128) / 127)


def pack_dir(v):
    x, y, z = (max(1, min(255, round(c * 127 + 128))) for c in v)
    return bytes((z, y, x, 128))


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
        at, n = u32(b, H_TEXTURES), u32(b, H_TEXTURES + 4)
        self.textures = [cstring(b, strings + u32(b, at + 8 * i)) for i in range(n)]
        at, n = u32(b, H_BONES), u32(b, H_BONES + 4)
        self.bones = [Bone(b, at + 4 + i * BONE, strings) for i in range(n)]
        at, n = u32(b, H_PARTS), u32(b, H_PARTS + 4)
        self.parts = [Part(b, at + i * PART) for i in range(n)]
        self.data = u32(b, H_DATA)
        self.submeshes = []
        at = u32(b, H_SUBMESHES)
        while u32(b, at) >> 16 == SUBMESH_TAG:
            self.submeshes.append(Submesh(b, at, self.data, self.scale, self.uv))
            at += SUBMESH

    def bone_matrix(self, i):
        """bone i's frame in the model: (3x3 rotation rows, translation)"""
        bone = self.bones[i]
        r, t = quat_matrix(bone.rotation), bone.position
        if bone.parent < 0:
            return r, t
        pr, pt = self.bone_matrix(bone.parent)
        return mat_mul(pr, r), add(pt, mat_vec(pr, t))

    def part_of(self, submesh):
        for p in self.parts:
            if p.vertex_offset == submesh.vertex_offset:
                return p
        return None


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


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


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


def obj(model):
    """the model as Wavefront .obj text: rigid parts placed by their bones, one group per submesh"""
    lines, base = [], 1
    for k, sm in enumerate(model.submeshes):
        part = model.part_of(sm)
        rot, pos = model.bone_matrix(part.bone) if part and sm.stride in RIGID else (None, None)
        name = model.bones[part.bone].name if part else f"submesh{k}"
        lines.append(f"g {name}")
        for v in sm.vertices:
            p = add(pos, mat_vec(rot, v["pos"])) if rot else v["pos"]
            n = mat_vec(rot, v["normal"]) if rot else v["normal"]
            lines.append("v %.6f %.6f %.6f" % p)
            lines.append("vt %.6f %.6f" % (v["uv"][0], 1 - v["uv"][1]))
            lines.append("vn %.4f %.4f %.4f" % n)
        for a, b, c in strip_triangles(sm.strip):  # .obj wants counter-clockwise front faces
            a, b, c = a + base, c + base, b + base
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        base += len(sm.vertices)
    return "\n".join(lines) + "\n"


def encode_vertex(v, stride, scale, uv):
    """a rigid vertex: pos (model units), uv, normal, and for 24 bytes tangent and binormal"""
    x, y, z = (int_clamp(c / scale) for c in v["pos"])
    s, t = (int_clamp((c - uv[0]) / uv[1]) for c in v["uv"])
    out = struct.pack("<4h2h", x, y, z, 1, s, t) + pack_dir(v["normal"])
    if stride == RIGID_STRIDE:
        out += pack_dir(v["tangent"]) + pack_dir(v["binormal"])
    return out


def int_clamp(f):
    i = round(f)
    if not -32768 <= i <= 32767:
        raise ValueError(f"{f:.1f} does not fit in 16 bits: the model is too large for its position scale")
    return i


def bounds(points):
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = max(math.dist(centre, p) for p in points)
    return lo, hi, centre, radius


def rebuild(template, meshes, scale=None):
    """template's bytes with new geometry: meshes[i] = (vertices, triangles) for submesh i, rigid, its
    vertices in its part's bone frame (dicts as decode_vertex gives them), triangles in strip order;
    scale (model units per step) defaults to the template's"""
    m = Model(template)
    if len(meshes) != len(m.submeshes):
        raise ValueError(f"the model has {len(m.submeshes)} submeshes, not {len(meshes)}")
    if any(sm.stride not in RIGID for sm in m.submeshes):
        raise ValueError("only rigid models can be rebuilt")
    b = bytearray(template)
    scale = scale or m.scale
    struct.pack_into("<f", b, H_SCALE, scale)
    data = bytearray()
    placed = []
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
        rot, pos = m.bone_matrix(part.bone)
        local = [v["pos"] for v in vertices]
        _, _, centre, radius = bounds(local)
        struct.pack_into("<3I", b, part.at, len(strip_triangles(strip)), part.bone, vo)
        struct.pack_into("<4f", b, part.at + 0x14, *centre, radius)
        placed += [add(pos, mat_vec(rot, p)) for p in local]
    lo, hi, centre, radius = bounds(placed)
    struct.pack_into("<6f", b, H_BOX, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    struct.pack_into("<4f", b, H_SPHERE, *centre, radius)
    data += b"\xcd" * (-len(data) % DATA_ALIGN)
    tail = m.data + len(data)
    struct.pack_into("<I", b, H_DATA + 4, len(data))
    struct.pack_into("<I", b, H_TAIL, tail)
    return bytes(b[: m.data]) + bytes(data) + template[u32(template, H_TAIL) :]


def info(model):
    out = [f"version {model.version}, position scale {model.scale:.6g}, uv {model.uv[0]:g} + s * {model.uv[1]:.6g}"]
    out += [f"texture {t}" for t in model.textures]
    for i, bone in enumerate(model.bones):
        out.append(
            f"bone {i} {bone.name}: parent {bone.parent}, at {tuple(round(c, 4) for c in bone.position)}, "
            f"rotation {tuple(round(c, 4) for c in bone.rotation)}"
        )
    for i, sm in enumerate(model.submeshes):
        part = model.part_of(sm)
        out.append(
            f"submesh {i}: material {sm.material}, {len(sm.vertices)} vertices of {sm.stride} bytes, "
            f"{len(strip_triangles(sm.strip))} triangles" + (f", bone {model.bones[part.bone].name}" if part else "")
        )
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("info", "obj"))
    ap.add_argument("model")
    ap.add_argument("target", nargs="?")
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
    dst.write_text(obj(model))
    print(dst)


if __name__ == "__main__":
    main()
