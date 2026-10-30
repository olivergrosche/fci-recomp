"""tools/xbg.py and tools/weapon_import.py on a synthetic model and glTF (no game data)"""

import base64
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weapon_import  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

SCALE = 1 / 32767


def template(bones=(("B_FRAME", -1, (0, 0, 0)), ("b_Magazine", 0, (0.2, 0.0, 0.05))), stride=24, version=1):
    """a model laid out like the games' weapons: one material, a diffuse and a normal texture, the bones
    (name, parent, position), one part and one submesh (a triangle) per bone"""
    n = len(bones)
    paths = [b"\\w\\gun\\gun_df.xbt", b"\\w\\gun\\gun_nt.xbt"] if stride == 24 else [b"\\w\\gun\\gun_3rd.xbt"]
    strings = b"".join(p + b"\0" for p in paths)
    tex_size = len(strings)
    strings += b"".join(name.encode() + b"\0" for name, _, _ in bones)
    names = [tex_size + sum(len(b[0]) + 1 for b in bones[:i]) for i in range(n)]
    b = bytearray(b"\xcd" * 0x400)
    b[:0xB0] = bytes(0xB0)
    b[0:4] = bytes((version, 0x09, 0x01, 0x01))
    struct.pack_into("<iI", b, 4, 0, 0xFFFFFFFF)
    struct.pack_into("<I", b, 0x0C, 0x4A00)
    material, textures, strings_at = 0xB0, 0xF0, 0x100
    bones_at = strings_at + len(strings) + 3 & ~3
    parts_at = bones_at + 4 + n * xbg.BONE
    subs_at = parts_at + n * xbg.PART
    data = subs_at + (n + 1) * xbg.SUBMESH + 31 & ~31
    struct.pack_into("<2I", b, xbg.H_MATERIALS, material, 1)
    struct.pack_into("<2I", b, xbg.H_TEXTURES, textures, len(paths))
    struct.pack_into("<2I", b, xbg.H_BONES, bones_at, n)
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
        struct.pack_into("<3I", b, parts_at + i * xbg.PART, 1, i, vo)
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
