"""tools/xbg.py and tools/weapon_import.py on synthetic models and a glTF (no game data)"""

import base64
import json
import math
from pathlib import Path
import struct
import sys
import zlib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weapon_import  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

SCALE = 1 / 32767


def template(
    bones=(("B_FRAME", -1, (0, 0, 0)), ("b_Magazine", 0, (0.2, 0.0, 0.05))), stride=24, version=1, part_bones=None
):
    """a model laid out like the games' weapons: one material, a diffuse and a normal texture, the bones
    (name, parent, position), one part (named after its bone in upper case, in the part index) and one
    submesh (a triangle) per bone; part_bones[i] is the bone part i hangs on (default bone i)"""
    n = len(bones)
    part_bones = part_bones or list(range(n))
    paths = [b"\\w\\gun\\gun_df.xbt", b"\\w\\gun\\gun_nt.xbt"] if stride == 24 else [b"\\w\\gun\\gun_3rd.xbt"]
    strings = b"".join(p + b"\0" for p in paths)
    tex_size = len(strings)
    strings += b"".join(name.encode() + b"\0" for name, _, _ in bones)
    names = [tex_size + sum(len(b[0]) + 1 for b in bones[:i]) for i in range(n)]
    upper = [len(strings) + sum(len(bones[j][0]) + 1 for j in part_bones[:i]) for i in range(n)]
    strings += b"".join(bones[j][0].upper().encode() + b"\0" for j in part_bones)
    b = bytearray(b"\xcd" * 0x1000)
    b[:0xB0] = bytes(0xB0)
    b[0:4] = bytes((version, 0x09, 0x01, 0x01))
    struct.pack_into("<iI", b, 4, 0, 0xFFFFFFFF)
    struct.pack_into("<I", b, 0x0C, 0x4A00)
    material, textures, strings_at = 0xB0, 0xF0, 0x100
    bones_at = strings_at + len(strings) + 3 & ~3
    index_at = bones_at + 4 + n * xbg.BONE
    parts_at = index_at + 8 * n
    subs_at = parts_at + n * xbg.PART
    data = subs_at + (n + 1) * xbg.SUBMESH + 31 & ~31
    struct.pack_into("<2I", b, xbg.H_MATERIALS, material, 1)
    struct.pack_into("<2I", b, xbg.H_TEXTURES, textures, len(paths))
    struct.pack_into("<2I", b, xbg.H_BONES, bones_at, n)
    struct.pack_into("<2I", b, xbg.H_PART_INDEX, index_at, n)
    struct.pack_into("<2I", b, xbg.H_PARTS, parts_at, n)
    struct.pack_into("<2I", b, xbg.H_SUBMESHES, subs_at, 1)
    struct.pack_into("<2I", b, xbg.H_STRINGS, strings_at, tex_size)
    struct.pack_into("<f2f", b, xbg.H_SCALE, SCALE, 0.5, 1 / 65536)
    for i in range(len(paths)):
        struct.pack_into("<2I", b, textures + 8 * i, sum(len(q) + 1 for q in paths[:i]), 0)
    b[strings_at : strings_at + len(strings)] = strings
    struct.pack_into("<I", b, bones_at, 0)
    for i, (_, parent, pos) in enumerate(bones):
        at = bones_at + 4 + i * xbg.BONE
        struct.pack_into("<3i4f3f3f", b, at, -1, -1, parent, 0, 0, 0, 1, *pos, 1, 1, 1)
        struct.pack_into("<ifHH", b, at + 0x34, -1, 1.0, 0xFF, names[i])
    vertex = struct.pack("<4h2h", 0, 0, 0, 1, 0, 0) + bytes((128, 128, 255, 128)) * (3 if stride == 24 else 1)
    blob = bytearray()
    for i in range(n):
        blob += b"\xcd" * (-len(blob) % 32)
        vo = len(blob)
        blob += vertex * 3
        io = len(blob)
        blob += struct.pack("<3H", 0, 1, 2)
        sub = subs_at + i * xbg.SUBMESH
        struct.pack_into("<5I", b, sub, 0xFFFF0000, vo, io, stride << 16 | 3, 0x53BF0000 | 3)
        b[sub + 20 : sub + 36] = b"\xff" * 8 + bytes(8)
        struct.pack_into("<5I", b, parts_at + i * xbg.PART, 1, i, vo, 0, 0x00010001)  # 1 submesh from i
        struct.pack_into("<Iii", b, parts_at + i * xbg.PART + 0x24, upper[i], -1, 0)
        name = bones[part_bones[i]][0].upper().encode()
        struct.pack_into("<IHH", b, index_at + 8 * i, zlib.crc32(name), i, part_bones[i])
    blob += b"\xcd" * (-len(blob) % 32)
    struct.pack_into("<2I", b, xbg.H_DATA, data, len(blob))
    struct.pack_into("<I", b, xbg.H_TAIL, data + len(blob))
    return bytes(b[:data]) + bytes(blob) + bytes(4)


def test_reads_bones_parts_and_textures():
    m = xbg.Model(template())
    assert [b.name for b in m.bones] == ["B_FRAME", "b_Magazine"]
    assert m.textures == ["\\w\\gun\\gun_df.xbt", "\\w\\gun\\gun_nt.xbt"]
    assert [m.part_of(sm).bone for sm in m.submeshes] == [0, 1]
    assert [round(c, 6) for c in m.bone_matrix(1)[1]] == [0.2, 0.0, 0.05]


def test_directions_are_d3dcolors():
    assert xbg.pack_dir((1, 0, 0)) == bytes((128, 128, 255, 128))  # z, y, x, w
    assert xbg.unpack_dir(xbg.pack_dir((0.6, -0.8, 0)), 0) == (76 / 127, -102 / 127, 0)


def test_strips_keep_every_triangle_and_its_winding():
    tris = [(0, 1, 2), (2, 1, 3), (2, 3, 4), (4, 3, 5), (7, 8, 9), (10, 12, 11)]
    strip = xbg.stripify(tris)

    def canon(t):
        return min(t, t[1:] + t[:1], t[2:] + t[:2])

    assert sorted(map(canon, xbg.strip_triangles(strip))) == sorted(map(canon, tris))
    assert len(strip) < 3 * len(tris)  # the first four share edges


def test_rebuild_places_vertices_on_their_bones():
    vertex = {"normal": (0, 0, 1), "tangent": (1, 0, 0), "binormal": (0, 1, 0)}
    frame = [dict(vertex, pos=p, uv=(0.25, 0.75)) for p in ((0, 0, 0), (0.1, 0, 0), (0, 0, 0.1), (0.1, 0, 0.1))]
    mag = [dict(vertex, pos=p, uv=(0.5, 0.5)) for p in ((0, 0, -0.1), (0.02, 0, -0.1), (0, 0, 0))]
    out = xbg.rebuild(template(), [(frame, [(0, 2, 1), (1, 2, 3)]), (mag, [(0, 2, 1)])])
    m = xbg.Model(out)
    assert [len(sm.vertices) for sm in m.submeshes] == [4, 3]
    assert [m.parts[i].triangles for i in range(2)] == [2, 1]
    assert [m.parts[i].vertex_offset for i in range(2)] == [sm.vertex_offset for sm in m.submeshes]
    assert all(sm.vertex_offset % 32 == 0 for sm in m.submeshes)
    v = m.submeshes[1].vertices[0]
    assert abs(v["pos"][2] + 0.1) < 1e-4 and abs(v["uv"][0] - 0.5) < 1e-4 and v["tangent"] == (1.0, 0.0, 0.0)
    box = struct.unpack_from("<6f", out, xbg.H_BOX)  # min, max per axis, the magazine placed on its bone
    assert abs(box[4] + 0.05) < 1e-4 and abs(box[1] - 0.22) < 1e-4
    assert out.endswith(bytes(4)) and xbg.u32(out, xbg.H_TAIL) == len(out) - 4
    assert "g b_Magazine" in xbg.obj(m)


def test_the_part_index_names_a_rigid_part_s_bone():
    bones = (("B_FRAME", -1, (0, 0, 0)), ("b_Magazine", 0, (0.2, 0, 0)), ("b_Slide", 0, (0, 0, 0.1)))
    m = xbg.Model(template(bones, part_bones=[0, 2, 1]))  # part 1 (submesh 1) hangs on bone 2
    assert [p.bone for p in m.parts] == [0, 2, 1] and [p.first for p in m.parts] == [0, 1, 2]
    assert [round(c, 6) for c in m.placed(m.submeshes[1])[0]["pos"]] == [0, 0, 0.1]
    assert "g b_Slide" in xbg.obj(m)


# A skinned model like the games' characters: a root bone like their BIP01 (a metre up, turned -90 degrees
# about z), then a chain of bones 0.1 apart along each one's x, the third turned 90 degrees about z.
ROOT_AT, ROOT_TURN = (0.0, 0.0, 1.0), -90
CHAIN = 11
TAIL = b"PHYS" + bytes(range(28))  # stands for a character's physics shapes


def chain_bones(n=CHAIN):
    """(name, parent, position, turn about z in degrees, skin matrix or -1)"""
    bones = [("BIP01", -1, ROOT_AT, ROOT_TURN, -1)]
    for i in range(1, n + 1):
        bones.append((f"Bone{i}", i - 1, (0.1 if i > 1 else 0.0, 0.0, 0.0), 90 if i == 3 else 0, i - 1))
    return bones


def in_root(bones):
    """each bone's turn about z (degrees) and origin in the root's frame"""
    out = []
    for _, parent, pos, turn, _ in bones:
        if parent < 0:
            out.append((0, (0.0, 0.0, 0.0)))
            continue
        a, (x, y, z) = out[parent]
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        out.append((a + turn, (x + c * pos[0] - s * pos[1], y + s * pos[0] + c * pos[1], z + pos[2])))
    return out


def model_point(p):
    """a point from the root's frame into the model: turned -90 degrees about z ((x, y) -> (y, -x)), raised"""
    return (p[1] + ROOT_AT[0], -p[0] + ROOT_AT[1], p[2] + ROOT_AT[2])


def skin_vertex(pos, slots, normal=(0, 0, 1), tangent=(1, 0, 0), binormal=(0, 1, 0), color=None):
    """a 28-byte vertex (32 with a colour, r g b a), pos in the root's frame; slots: [(slot, weight byte)]"""
    (s0, w0), (s1, w1) = (list(slots) + [(0, 0)])[:2]
    out = struct.pack("<4h2h", *(round(c / SCALE) for c in pos), 1, 0, 0) + bytes((w0, w1, 4 * s0, 4 * s1))
    out += xbg.pack_dir(normal)
    if color:
        out += bytes((color[2], color[1], color[0], color[3]))
    return out + xbg.pack_dir(tangent) + xbg.pack_dir(binormal)


def skinned_template():
    """materials 0 (shader ..53bf, 28-byte vertices) and 1 (..4507, 32 bytes with a colour); part 0
    BODY_LOD0: a triangle on bones 1-3 (vertex 1 at 0.2 along the chain, 128/255 on bone 2 and 127/255 on
    bone 1), part 1 LOGO: a triangle on bone 4 with red vertices; the physics tail TAIL"""
    bones = chain_bones()
    paths = [b"\\c\\body_df.xbt", b"\\c\\logo_df.xbt"]
    strings = b"".join(p + b"\0" for p in paths)
    tex_size = len(strings)
    names = []
    for name, *_ in bones:
        names.append(len(strings))
        strings += name.encode() + b"\0"
    parts = [b"BODY_LOD0", b"LOGO"]
    part_names = []
    for p in parts:
        part_names.append(len(strings))
        strings += p + b"\0"
    b = bytearray(b"\xcd" * 0x2000)
    b[:0xB0] = bytes(0xB0)
    b[0:4] = bytes((0, 0x09, 0x01, 0x01))
    struct.pack_into("<iII", b, 4, 0, 0xFFFFFFFF, 0x4A00)
    materials, textures, strings_at = 0xB0, 0x110, 0x120
    bones_at = strings_at + len(strings) + 3 & ~3
    skin_at = bones_at + 4 + len(bones) * xbg.BONE
    index_at = skin_at + CHAIN * xbg.MATRIX
    parts_at = index_at + 8 * len(parts)
    subs_at = parts_at + len(parts) * xbg.PART
    data = subs_at + 2 * xbg.SUBMESH + 4 + 15 & ~15
    for k, (shader, tex) in enumerate(((0x2B8453BF, 0), (0x23424507, 1))):
        struct.pack_into("<3I2i", b, materials + k * xbg.MATERIAL, shader, 0xFFFFFFFF, 0xFF000000, tex, -1)
        struct.pack_into("<ifiiiii", b, materials + k * xbg.MATERIAL + 0x14, -1, 1.0, -1, -1, -1, 0x21, 0)
    for i in range(len(paths)):
        struct.pack_into("<2I", b, textures + 8 * i, sum(len(q) + 1 for q in paths[:i]), 0)
    b[strings_at : strings_at + len(strings)] = strings
    struct.pack_into("<I", b, bones_at, 0)
    frames = in_root(bones)
    for i, (_, parent, pos, turn, skin) in enumerate(bones):
        at = bones_at + 4 + i * xbg.BONE
        half = math.radians(turn) / 2
        child = i + 1 if i < CHAIN else -1
        struct.pack_into("<3i4f3f3f", b, at, child, -1, parent, 0, 0, math.sin(half), math.cos(half), *pos, 1, 1, 1)
        struct.pack_into("<ifHHII", b, at + 0x34, skin, 1.0, 0xFF, names[i], 0, 0)
        if skin >= 0:  # the inverse of the bone's frame in the root's, for row vectors: turn, -turned origin
            a, (x, y, z) = frames[i]
            c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
            m = (c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, -(c * x + s * y), -(-s * x + c * y), -z, 1)
            struct.pack_into("<16f", b, skin_at + skin * xbg.MATRIX, *m)
    body = [
        skin_vertex((0.0, 0.0, 0.0), [(0, 255)]),
        skin_vertex((0.2, 0.0, 0.0), [(1, 128), (0, 127)]),
        skin_vertex((0.2, 0.0, 0.05), [(2, 255)]),
    ]
    red = (255, 0, 0, 0)
    logo = [skin_vertex((0.2, 0.1 * k, 0.1), [(0, 255)], color=red) for k in range(1, 4)]
    blob = bytearray()
    for k, (vertices, stride, palette) in enumerate(((body, 28, [1, 2, 3]), (logo, 32, [4]))):
        blob += b"\xcd" * (-len(blob) % 32)
        vo = len(blob)
        blob += b"".join(vertices)
        io = len(blob)
        blob += struct.pack("<3H", 0, 1, 2)
        sub = subs_at + k * xbg.SUBMESH
        tag = (0x53BF, 0x4507)[k]
        struct.pack_into("<5I", b, sub, 0xFFFF0000 | k, vo, io, stride << 16 | 3, tag << 16 | 3)
        b[sub + 20 : sub + 36] = bytes(palette + [0xFF] * (8 - len(palette))) + bytes(8)
        struct.pack_into("<5I", b, parts_at + k * xbg.PART, 1, k, vo, 0, 0x00010001)
        struct.pack_into("<Iii", b, parts_at + k * xbg.PART + 0x24, part_names[k], (0, -1)[k], 0)  # its LOD
        struct.pack_into("<IHH", b, index_at + 8 * k, zlib.crc32(parts[k]), k, 0xFFFF)
    blob += b"\xcd" * (-len(blob) % 16)
    struct.pack_into("<2I", b, xbg.H_MATERIALS, materials, 2)
    struct.pack_into("<2I", b, xbg.H_TEXTURES, textures, len(paths))
    struct.pack_into("<2I", b, xbg.H_BONES, bones_at, len(bones))
    struct.pack_into("<2I", b, xbg.H_SKIN, skin_at, CHAIN)
    struct.pack_into("<2I", b, xbg.H_PART_INDEX, index_at, len(parts))
    struct.pack_into("<2I", b, xbg.H_PARTS, parts_at, len(parts))
    struct.pack_into("<2I", b, xbg.H_SUBMESHES, subs_at, 1)
    struct.pack_into("<2I", b, xbg.H_DATA, data, len(blob))
    struct.pack_into("<2I", b, xbg.H_TAIL, data + len(blob) + 16, 0)
    struct.pack_into("<2I", b, xbg.H_STRINGS, strings_at, tex_size)
    struct.pack_into("<f2f", b, xbg.H_SCALE, SCALE, 0.5, 1 / 65536)
    return bytes(b[:data]) + bytes(blob) + b"\xcd" * 16 + TAIL


def close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_vertex_layouts_by_size():
    assert xbg.fields(28, True) == ("normal", "tangent", "binormal")
    assert xbg.fields(32, True) == ("normal", "color", "tangent", "binormal")
    assert xbg.fields(20, True) == ("normal",) and xbg.fields(16, True) == ()
    assert xbg.fields(24, False) == ("normal", "tangent", "binormal") and xbg.fields(16, False) == ("normal",)
    with pytest.raises(ValueError):
        xbg.fields(18, True)


def test_reads_skinned_vertices():
    m = xbg.Model(skinned_template())
    body, logo = m.submeshes
    assert m.skinned and body.skinned and [p.bone for p in m.parts] == [None, None]
    assert [p.name for p in m.parts] == ["BODY_LOD0", "LOGO"] and [p.lod for p in m.parts] == [0, -1]
    assert body.bones == [1, 2, 3] and [b.skin for b in m.bones[:3]] == [-1, 0, 1]
    assert [m.materials[sm.material].diffuse for sm in m.submeshes] == [0, 1]
    assert body.vertices[0]["skin"] == [(1, 1.0)]
    assert body.vertices[1]["skin"] == [(2, 128 / 255), (1, 127 / 255)]  # byte 12 goes with slot byte 14
    assert logo.vertices[0]["color"] == (255, 0, 0, 0) and close(logo.vertices[0]["tangent"], (1, 0, 0), 0.01)


def test_skinned_vertices_are_stored_in_the_root_frame():
    m = xbg.Model(skinned_template())
    v = m.placed(m.submeshes[0])[2]
    assert close(v["pos"], model_point((0.2, 0, 0.05)))
    assert close(v["tangent"], (0, -1, 0), 0.01) and close(v["normal"], (0, 0, 1), 0.01)


def test_skin_matrices_undo_the_bind_pose():
    m = xbg.Model(skinned_template())
    frames = in_root(chain_bones())
    for bone in range(1, CHAIN + 1):  # each bone's own origin goes to its frame's origin
        rot, t = m.skin_matrix(bone)
        assert close(xbg.add(xbg.mat_vec(rot, frames[bone][1]), t), (0, 0, 0), 1e-5)
    for sm in m.submeshes:
        for posed, placed in zip(m.posed(sm, m.frames()), m.placed(sm)):
            assert close(posed["pos"], placed["pos"], 1e-5)


def test_posing_moves_vertices_with_their_weights():
    m = xbg.Model(skinned_template())
    half = math.radians(90) / 2  # bone 2 turns 90 degrees about its z, at 0.1 along the chain
    frames = m.frames({2: (0, 0, math.sin(half), math.cos(half))})
    v0, v1, v2 = m.posed(m.submeshes[0], frames)
    assert close(v0["pos"], model_point((0, 0, 0)))  # on bone 1: stays
    assert close(v2["pos"], model_point((0.1, 0.1, 0.05)))  # on bone 3, a child of 2: turned about (0.1, 0, 0)
    w = 128 / 255  # half on bone 2 (from (0.2, 0) to (0.1, 0.1)), half on bone 1 (stays at (0.2, 0))
    assert close(v1["pos"], model_point((0.1 * w + 0.2 * (1 - w), 0.1 * w, 0)))


def ribbon(m):
    """a strip of quads along the whole chain in the model, each edge on its bone (0.7) and the next (0.3)"""
    frames = m.frames()
    vertices, triangles = [], []
    for bone in range(1, CHAIN + 1):
        nxt = min(bone + 1, CHAIN)
        for dz in (-0.02, 0.02):
            pos = xbg.add(frames[bone][1], (0, 0, dz))
            skin = [(bone, 0.7), (nxt, 0.3)] if nxt != bone else [(bone, 1.0)]
            uv = (bone / CHAIN, 0.5 + dz)
            vertices.append(
                {"pos": pos, "uv": uv, "normal": (0, 0, 1), "tangent": (1, 0, 0), "binormal": (0, 1, 0), "skin": skin}
            )
        if bone > 1:
            a, b, c, d = len(vertices) - 4, len(vertices) - 3, len(vertices) - 2, len(vertices) - 1
            triangles += [(a, b, c), (c, b, d)]
    return vertices, triangles


def test_rebuild_skinned_splits_palettes_and_keeps_the_rest():
    src = skinned_template()
    m = xbg.Model(src)
    vertices, triangles = ribbon(m)
    out = xbg.rebuild_skinned(src, [[(0, vertices, triangles)], None])
    n = xbg.Model(out)
    body = n.submeshes[: n.parts[0].count]
    assert len(body) >= 2 and all(len(sm.bones) <= xbg.PALETTE for sm in body)  # 11 bones: split
    assert {b for sm in body for b in sm.bones} == set(range(1, CHAIN + 1))
    assert n.parts[0].triangles == len(triangles) == sum(len(xbg.strip_triangles(sm.strip)) for sm in body)
    assert n.parts[1].first == len(body) and n.parts[1].count == 1
    assert n.submeshes[-1].raw == m.submeshes[1].raw and n.submeshes[-1].palette == m.submeshes[1].palette
    assert all(sm.vertex_tag == 0x53BF and sm.stride == 28 for sm in body)

    def key(v):
        return tuple(round(c, 3) for c in v["pos"]), tuple(sorted((b, round(w, 2)) for b, w in v["skin"]))

    want = sorted(tuple(sorted(key(vertices[i]) for i in t)) for t in triangles)
    got = sorted(
        tuple(sorted(key(v[i]) for i in t))
        for sm in body
        for v in [n.placed(sm)]
        for t in xbg.strip_triangles(sm.strip)
    )
    assert got == want
    assert out.endswith(TAIL) and out[xbg.u32(out, xbg.H_TAIL) :] == TAIL
    assert n.data % 16 == 0 and all(sm.vertex_offset % 32 == 0 for sm in n.submeshes)
    box = struct.unpack_from("<6f", out, xbg.H_BOX)
    assert close((box[0], box[1]), (min(v["pos"][0] for v in vertices), max(v["pos"][0] for v in vertices)), 1e-4)


def test_rebuild_skinned_round_trips_a_model():
    src = skinned_template()
    m = xbg.Model(src)
    out = xbg.rebuild_skinned(src, [xbg.mesh_of(m, p) for p in m.parts])
    n = xbg.Model(out)
    for a, b in zip(m.submeshes, n.submeshes):
        for va, vb in zip(m.placed(a), n.placed(b)):
            assert close(va["pos"], vb["pos"], 1e-5) and sorted(va["skin"]) == sorted(vb["skin"])
            assert va.get("color") == vb.get("color")


def test_rebuild_skinned_at_a_new_scale_keeps_the_kept_parts_in_place():
    src = skinned_template()
    m = xbg.Model(src)
    vertices, triangles = ribbon(m)
    n = xbg.Model(xbg.rebuild_skinned(src, [[(0, vertices, triangles)], None], scale=2 / 32767))
    assert abs(n.scale - 2 / 32767) < 1e-9
    for a, b in zip(m.placed(m.submeshes[1]), n.placed(n.submeshes[-1])):
        assert close(a["pos"], b["pos"], 1e-4) and a["color"] == b["color"]


def test_rebuild_skinned_refuses_bones_without_a_skin_matrix():
    src = skinned_template()
    vertices, triangles = ribbon(xbg.Model(src))
    vertices[0]["skin"] = [(0, 1.0)]  # the root has no skin matrix, as BIP01 in the games
    with pytest.raises(ValueError, match="BIP01"):
        xbg.rebuild_skinned(src, [[(0, vertices, triangles)], None])


def test_influences_keep_the_two_largest():
    (b0, w0), (b1, w1) = xbg.influences([(1, 0.5), (2, 0.3), (3, 0.2)])
    assert (b0, b1) == (1, 2) and close((w0, w1), (0.625, 0.375), 1e-9)
    assert xbg.pack_skin([(5, 0.25), (7, 0.75)], {5: 1, 7: 3}) == bytes((191, 64, 12, 4))
    assert xbg.pack_skin([(5, 1.0)], {5: 2}) == bytes((255, 0, 8, 0))


def gltf_quad(tmp_path):
    """a 2 x 1 quad facing -y (the glTF's z after the axes below), one material with no textures"""
    pos = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
    blob = b"".join(struct.pack("<3f", *p) for p in pos)
    blob += b"".join(struct.pack("<3f", 0, 0, 1) for _ in pos)
    blob += b"".join(struct.pack("<2f", p[0] / 2, 1 - p[1]) for p in pos)
    blob += struct.pack("<6H", 0, 1, 2, 0, 2, 3)
    views = [(0, 48), (48, 48), (96, 32), (128, 12)]
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1], "roughnessFactor": 0.5}}],
        "buffers": [
            {"byteLength": len(blob), "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode()}
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": o, "byteLength": n} for o, n in views],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 4, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 6, "type": "SCALAR"},
        ],
    }
    (tmp_path / "quad.gltf").write_text(json.dumps(g))


def test_import_puts_a_gltf_on_the_template(tmp_path):
    gltf_quad(tmp_path)
    folder = tmp_path / "extract" / "w" / "gun"
    folder.mkdir(parents=True)
    (folder / "gun.xbg").write_bytes(template())
    cfg = {
        "source": "quad.gltf",
        "template": "extract",
        "model": "w/gun/gun.xbg",
        "axes": ["x", "-z", "y"],
        "scale": 0.1,
        "anchor": {"source": [0, 0, 0], "target": [0.01, 0.02, 0.03]},
        "texture": {"size": 64, "gloss": [100, 200]},
        "out": "out",
    }
    weapon_import.build(cfg, tmp_path)
    m = xbg.Model((tmp_path / "out" / "w" / "gun" / "gun.xbg").read_bytes())
    frame, mag = m.submeshes
    assert len(frame.vertices) == 4 and len(xbg.strip_triangles(frame.strip)) == 2
    assert len(mag.vertices) == 3  # no piece for the magazine: the placeholder
    xs = sorted(round(v["pos"][0], 3) for v in frame.vertices)
    zs = sorted(round(v["pos"][2], 3) for v in frame.vertices)
    assert xs == [0.01, 0.01, 0.21, 0.21] and zs == [0.03, 0.03, 0.13, 0.13]
    v = frame.vertices[0]
    assert v["normal"][1] < -0.99  # the glTF's +z is the game's -y
    p = {i: frame.vertices[i]["pos"] for i in range(4)}
    n = v["normal"]
    for a, b, c in xbg.strip_triangles(frame.strip):  # the games' front faces: clockwise to the normal
        e1, e2 = weapon_import.sub(p[b], p[a]), weapon_import.sub(p[c], p[a])
        assert weapon_import.dot(weapon_import.cross(e1, e2), n) < 0
    for vert in frame.vertices:  # the binormal along -v, the tangent along +u
        assert vert["binormal"][2] > 0.99 and vert["tangent"][0] > 0.99
    df = (tmp_path / "out" / "w" / "gun" / "gun_df.xbt").read_bytes()
    nt = (tmp_path / "out" / "w" / "gun" / "gun_nt.xbt").read_bytes()
    assert xbt.header(df)[:2] == (64, 64) and xbt.header(df)[3] == weapon_import.DXT5 and xbt.header(df)[4] == 5
    assert xbt.header(nt)[3] == weapon_import.DXT1


def test_a_new_material_and_submesh_keep_the_rest():
    b = template()
    paths = ["\\w\\gun\\gun_counter.xbt", "\\w\\gun\\gun_counter_nt.xbt"]
    out, mat = xbg.add_material(b, 0, paths)
    out = xbg.add_submesh(out, 0, mat, 24)
    m, m0 = xbg.Model(out), xbg.Model(b)
    assert mat == 1 and m.textures == m0.textures + paths
    assert (m.materials[1].diffuse, m.materials[1].bump, m.materials[1].shader) == (2, 3, m0.materials[0].shader)
    assert [x.name for x in m.bones] == [x.name for x in m0.bones]
    assert [p.name for p in m.parts] == [p.name for p in m0.parts]
    assert [(p.first, p.count) for p in m.parts] == [(0, 2), (2, 1)]  # the new one after the frame's
    assert [(sm.material, len(sm.vertices)) for sm in m.submeshes] == [(0, 3), (1, 0), (0, 3)]
    assert m.submeshes[2].vertices == m0.submeshes[1].vertices
    for h in xbg.OFFSETS:  # every block moved by whole 16-byte steps
        old, new = xbg.u32(b, h), xbg.u32(out, h)
        assert (old in (0, 0xFFFFFFFF) and new == old) or (new - old) % 16 == 0
    v = m.submeshes[0].vertices[0]
    meshes = [(sm.vertices, xbg.strip_triangles(sm.strip)) for sm in m.submeshes]
    meshes[1] = ([dict(v, pos=(0, 0, 0)), dict(v, pos=(0.01, 0, 0)), dict(v, pos=(0, 0, 0.01))], [(0, 2, 1)])
    built = xbg.Model(xbg.rebuild(out, meshes))
    assert len(built.submeshes[1].vertices) == 3 and built.parts[0].triangles == 2


def gltf_quads(tmp_path, quads):
    """quads (corner positions, material name) facing +z, each a primitive, uv over the whole texture"""
    blob, views, accessors, prims, materials = b"", [], [], [], []
    for corners, name in quads:
        for data, kind in (
            (b"".join(struct.pack("<3f", *p) for p in corners), "VEC3"),
            (b"".join(struct.pack("<3f", 0, 0, 1) for _ in corners), "VEC3"),
            (b"".join(struct.pack("<2f", u, v) for u, v in ((0, 1), (1, 1), (1, 0), (0, 0))), "VEC2"),
            (struct.pack("<6H", 0, 1, 2, 0, 2, 3) + bytes(4), "SCALAR"),
        ):
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data) if kind != "SCALAR" else 12})
            accessors.append(
                {
                    "bufferView": len(views) - 1,
                    "componentType": 5123 if kind == "SCALAR" else 5126,
                    "type": kind,
                    "count": 6 if kind == "SCALAR" else 4,
                }
            )
            blob += data
        a = len(accessors) - 4
        prims.append(
            {
                "attributes": {"POSITION": a, "NORMAL": a + 1, "TEXCOORD_0": a + 2},
                "indices": a + 3,
                "material": len(materials),
            }
        )
        materials.append({"name": name, "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.4, 0.6, 1]}})
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": prims}],
        "materials": materials,
        "buffers": [
            {"byteLength": len(blob), "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode()}
        ],
        "bufferViews": views,
        "accessors": accessors,
    }
    (tmp_path / "quads.gltf").write_text(json.dumps(g))


def test_a_counter_display_gets_its_own_texture(tmp_path):
    gun = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
    screen = [(0.5, 0.2, 0.1), (1.5, 0.2, 0.1), (1.5, 0.7, 0.1), (0.5, 0.7, 0.1)]
    gltf_quads(tmp_path, [(gun, "gun"), (screen, "screen")])
    folder = tmp_path / "extract" / "w" / "gun"
    folder.mkdir(parents=True)
    (folder / "gun.xbg").write_bytes(template())
    cfg = {
        "source": "quads.gltf",
        "template": "extract",
        "axes": ["x", "-z", "y"],
        "scale": 0.1,
        "anchor": {"source": [0, 0, 0], "target": [0, 0, 0]},
        "texture": {"size": 64, "gloss": [100, 200]},
        "out": "plain",
        "drop_materials": ["screen"],
        "models": [{"model": "w/gun/gun.xbg"}],
    }
    weapon_import.build(cfg, tmp_path)  # the same gun without the display
    counter = {
        "size": [32, 16],
        "groups": [{"materials": ["screen"], "rect": [0.5, 0.0, 1.0, 1.0], "flip": "y"}],
        "digits": [[0.5, 0.0, 0.75, 1.0], [0.75, 0.0, 1.0, 1.0]],
        "compass": [0.0, 0.0, 0.5, 1.0],
    }
    cfg.update(out="out", drop_materials=[], models=[{"model": "w/gun/gun.xbg", "counter": counter}])
    weapon_import.build(cfg, tmp_path)
    out = tmp_path / "out" / "w" / "gun"
    m = xbg.Model((out / "gun.xbg").read_bytes())
    assert m.textures[2:] == ["\\w\\gun\\gun_counter.xbt", "\\w\\gun\\gun_counter_nt.xbt"]
    frame, display, mag = m.submeshes
    assert (frame.material, display.material, mag.material) == (0, 1, 0)
    assert len(xbg.strip_triangles(frame.strip)) == 2 and len(xbg.strip_triangles(display.strip)) == 2
    uvs = sorted((round(v["uv"][0], 3), round(v["uv"][1], 3)) for v in display.vertices)
    assert uvs == [(0.5, 0.0), (0.5, 1.0), (1.0, 0.0), (1.0, 1.0)]
    top = [v for v in display.vertices if v["uv"][1] < 0.5]  # flipped: the glTF's v 1 (its lower edge) at 0
    assert all(abs(v["pos"][2] - 0.02) < 1e-3 for v in top)
    # the atlas is the gun's alone, as without the display
    assert (out / "gun_df.xbt").read_bytes() == (tmp_path / "plain" / "w" / "gun" / "gun_df.xbt").read_bytes()
    raw = (out / "gun_counter.xbt").read_bytes()
    w, h, size, fmt, levels, faces = xbt.header(raw)
    assert (w, h, fmt, levels, faces) == (32, 16, weapon_import.A8R8G8B8, 6, 1)
    level0 = xbt.swizzle(raw[32 : 32 + w * h * 4], w, h, 4, unswizzle=True)
    stream = b"".join(level0[4 * i : 4 * i + 3] for i in range(18))
    assert stream[:6] == b"FCIC\x01\x03" and stream[50:54] == b"CTR1"
    assert struct.unpack_from("<12H", stream, 6) == (16, 0, 24, 16, 24, 0, 32, 16, 0, 0, 16, 16)
    assert all(level0[4 * i + 3] == 255 for i in range(18))
    assert xbt.header((out / "gun_counter_nt.xbt").read_bytes())[3] == weapon_import.DXT1
