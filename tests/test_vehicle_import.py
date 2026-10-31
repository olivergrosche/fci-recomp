"""tools/vehicle_import.py on a synthetic glTF vehicle and a synthetic game folder (no game or Halo data)"""

import base64
import io
import json
import math
from pathlib import Path
import struct
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dat2  # noqa: E402
from test_xbg import close, template  # noqa: E402
import vehicle_import as vi  # noqa: E402
import weapon_import as wi  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

# the source, in the game's axes (X right, Y forward, Z up; "axes": ["x", "y", "z"]): tires 0.2 wide and 0.4
# across, 1.2 apart along Y and 0.8 across, their middle at (0, 0, 0.2); a hull box; a gun box
TIRES = {
    "tire fl": (-0.4, 0.6, 0.2),
    "tire fr": (0.4, 0.6, 0.2),
    "tire bl": (-0.4, -0.6, 0.2),
    "tire br": (0.4, -0.6, 0.2),
}
BOXES = {name: (c, (0.1, 0.2, 0.2), 1) for name, c in TIRES.items()}
BOXES["hull"] = ((0.0, 0.0, 0.5), (0.5, 0.9, 0.2), 0)
BOXES["gun"] = ((0.0, -0.5, 0.8), (0.05, 0.3, 0.05), 0)
# the template: wheels 3.2 apart and 1.7 across, 0.45 in radius, their middle at (0, 0, 0.45)
WHEELS = {
    "Wheel1": (-0.85, 1.6, 0.45),
    "Wheel2": (0.85, 1.6, 0.45),
    "Wheel3": (-0.85, -1.6, 0.45),
    "Wheel4": (0.85, -1.6, 0.45),
}
PATH = "v/car.xbg"


def box(centre, half):
    """a box's 24 vertices (positions, normals, uvs) and 12 triangles, counter-clockwise from outside"""
    pos, nrm, uv, idx = [], [], [], []
    for axis in range(3):
        for sign in (-1, 1):
            n = [0.0, 0.0, 0.0]
            n[axis] = sign
            u, v = [k for k in range(3) if k != axis]
            corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
            if sign < 0:
                corners.reverse()
            base = len(pos)
            for a, b in corners:
                p = list(centre)
                p[axis] += sign * half[axis]
                p[u] += a * half[u]
                p[v] += b * half[v]
                pos.append(p)
                nrm.append(n)
                uv.append(((a + 1) / 2, (b + 1) / 2))
            idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return pos, nrm, uv, idx


def gltf(tmp_path):
    blob, views, accessors, meshes, nodes = bytearray(), [], [], [], []

    def put(data, kind, count, comp=5126):
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        blob.extend(bytes(-len(blob) % 4))
        accessors.append({"bufferView": len(views) - 1, "componentType": comp, "count": count, "type": kind})
        return len(accessors) - 1

    for name, (centre, half, material) in BOXES.items():
        pos, nrm, uv, idx = box(centre, half)
        attrs = {
            "POSITION": put(b"".join(struct.pack("<3f", *p) for p in pos), "VEC3", len(pos)),
            "NORMAL": put(b"".join(struct.pack("<3f", *n) for n in nrm), "VEC3", len(nrm)),
            "TEXCOORD_0": put(b"".join(struct.pack("<2f", *t) for t in uv), "VEC2", len(uv)),
        }
        ind = put(struct.pack(f"<{len(idx)}H", *idx), "SCALAR", len(idx), 5123)
        meshes.append({"primitives": [{"attributes": attrs, "indices": ind, "material": material}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {"name": "body", "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.5, 0.2, 1]}},
            {"name": "rubber", "pbrMetallicRoughness": {"baseColorFactor": [0.1, 0.1, 0.1, 1]}},
        ],
        "buffers": [{"byteLength": len(blob), "uri": "data:;base64," + base64.b64encode(bytes(blob)).decode()}],
        "bufferViews": views,
        "accessors": accessors,
    }
    (tmp_path / "car.gltf").write_text(json.dumps(g))


def vertex(p):
    return {"pos": p, "uv": (0.5, 0.5), "normal": (0, 0, 1), "tangent": (1, 0, 0), "binormal": (0, 1, 0)}


def car_template():
    """a vehicle: root, hull2, four wheel bones with a box 0.3 wide and 0.9 across each, a turret_mesh at the
    origin; one material (gun_df / gun_nt)"""
    bones = [("SCENE ROOT", -1, (0, 0, 0)), ("hull2", 0, (0, 0, 1.0))]
    bones += [(name, 0, at) for name, at in WHEELS.items()]
    bones += [("turret_mesh", 0, (0, 0, 0))]
    t = bytearray(template(bones=tuple(bones)))
    at = struct.unpack_from("<I", t, xbg.H_MATERIALS)[0]
    struct.pack_into("<2I", t, at, 0x2B8453BF, 0xFFFFFFFF)  # a bump-mapped shader, white
    struct.pack_into("<i", t, at + 0x0C, 0)  # diffuse gun_df
    struct.pack_into("<i", t, at + 0x14, 1)  # bump gun_nt
    t = bytes(t)
    meshes = []
    for name, _, _ in bones:
        if name.startswith("Wheel"):
            pos, _, _, idx = box((0, 0, 0), (0.15, 0.45, 0.45))
            meshes.append(([vertex(tuple(p)) for p in pos], [tuple(idx[k : k + 3]) for k in range(0, len(idx), 3)]))
        else:
            meshes.append(([vertex((0, 0, 0)), vertex((0.01, 0, 0)), vertex((0, 0, 0.01))], [(0, 1, 2)]))
    return xbg.rebuild(t, meshes, 4 / 32767)


def texture():
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (90, 90, 90)).save(out, "PNG")
    return wi.dxt_xbt(Image.open(out), wi.DXT1)


def game(tmp_path):
    """levels/L1 holds the car and its textures, levels/L2 only the textures"""
    files = {PATH: car_template(), "w/gun/gun_df.xbt": texture(), "w/gun/gun_nt.xbt": texture()}
    for level, names in (("L1", files), ("L2", [p for p in files if p.endswith(".xbt")])):
        folder = tmp_path / "game" / "levels" / level
        folder.mkdir(parents=True)
        dat, fat = dat2.build({dat2.name_hash(p): files[p] for p in names})
        (folder / f"{level.lower()}.dat").write_bytes(dat)
        (folder / f"{level.lower()}.fat").write_bytes(fat)


def config(tmp_path, **extra):
    gltf(tmp_path)
    game(tmp_path)
    cfg = {
        "game": "game",
        "out": "mod",
        "source": "car.gltf",
        "axes": ["x", "y", "z"],
        "texture": {"size": 64},
        "wheels": {"Wheel1": "tire fl", "Wheel2": "tire fr", "Wheel3": "tire bl", "Wheel4": "tire br"},
        "models": [
            {
                "model": PATH,
                "parts": [
                    {"bone": "Wheel1", "wheel": "tire fl"},
                    {"bone": "Wheel2", "wheel": "tire fr"},
                    {"bone": "Wheel3", "wheel": "tire bl"},
                    {"bone": "Wheel4", "wheel": "tire br"},
                    {
                        "bone": "turret_mesh",
                        "nodes": ["gun"],
                        "anchor": {"source": [0, -0.5, 0.8], "target": [0, 0.5, 0.1]},
                        "scale": 2.0,
                    },
                    {"bone": "hull2", "rest": True},
                ],
            }
        ],
        "mod": {"name": "Car", "group": "Test"},
    }
    cfg.update(extra)
    return cfg


def built(tmp_path):
    return xbg.Model((tmp_path / "mod" / "levels" / "L1" / "l1" / PATH).read_bytes())


def placed_points(model, bone_name):
    bone = vi.bone_index(model, bone_name)
    return [v["pos"] for sm in vi.bone_submeshes(model, bone) for v in model.placed(sm)]


def test_tires_land_on_the_template_wheels(tmp_path):
    vi.build(config(tmp_path), tmp_path)
    m = built(tmp_path)
    for bone, centre in WHEELS.items():
        lo, hi = vi.box_of(placed_points(m, bone))
        assert close(vi.middle(lo, hi), centre)
        assert abs((hi[1] - lo[1]) / 2 - 0.45) < 1e-3 and abs((hi[2] - lo[2]) / 2 - 0.45) < 1e-3
        assert abs((hi[0] - lo[0]) - 0.2 * 0.45 / 0.2) < 1e-3  # scaled as its radius was


def test_the_body_scales_by_the_wheelbase_and_narrows_by_width(tmp_path):
    vi.build(config(tmp_path, body={"scale": "wheelbase", "width": 0.9}), tmp_path)
    lo, hi = vi.box_of(placed_points(built(tmp_path), "hull2"))
    s = 3.2 / 1.2  # the template's wheelbase over the source's
    assert close(hi, (0.5 * s * 0.9, 0.9 * s, 0.45 + 0.5 * s))
    assert close(lo, (-0.5 * s * 0.9, -0.9 * s, 0.45 + 0.1 * s))


def test_anchored_parts_go_to_their_target_in_the_bone_frame(tmp_path):
    vi.build(config(tmp_path), tmp_path)
    lo, hi = vi.box_of(placed_points(built(tmp_path), "turret_mesh"))
    assert close(vi.middle(lo, hi), (0, 0.5, 0.1))
    assert close(hi, (0.1, 0.5 + 0.6, 0.1 + 0.1))


def test_files_go_where_the_vehicle_is(tmp_path):
    vi.build(config(tmp_path), tmp_path)
    mod = tmp_path / "mod"
    l1 = mod / "levels" / "L1" / "l1"
    assert (l1 / PATH).is_file() and not (mod / "levels" / "L2").exists()
    df, nt = (l1 / "w/gun/gun_df.xbt").read_bytes(), (l1 / "w/gun/gun_nt.xbt").read_bytes()
    assert xbt.header(df)[3] == wi.DXT1 and xbt.header(nt)[3] == wi.DXT1  # the originals' format
    assert (mod / "mod.ini").read_text().startswith("name = Car")
    listed = (mod / ".files").read_text().split()
    assert f"levels/L1/l1/{PATH}" in listed and "levels/L1/l1/w/gun/gun_df.xbt" in listed


def test_the_physics_tail_and_bones_stay(tmp_path):
    vi.build(config(tmp_path), tmp_path)
    old, new = xbg.Model(car_template()), built(tmp_path)
    assert [(b.name, b.position, b.rotation) for b in old.bones] == [
        (b.name, b.position, b.rotation) for b in new.bones
    ]
    tail = struct.unpack_from("<I", car_template(), xbg.H_TAIL)[0]
    out = (tmp_path / "mod" / "levels" / "L1" / "l1" / PATH).read_bytes()
    assert out[struct.unpack_from("<I", out, xbg.H_TAIL)[0] :] == car_template()[tail:]


def test_double_sided_parts_get_a_back(tmp_path):
    cfg = config(tmp_path)
    cfg["models"][0]["parts"][4]["double_sided"] = True
    vi.build(cfg, tmp_path)
    sm = vi.bone_submeshes(built(tmp_path), vi.bone_index(built(tmp_path), "turret_mesh"))[0]
    assert len(xbg.strip_triangles(sm.strip)) == 24  # a box's 12 and their backs


def test_helpers_move_through_the_body_fit(tmp_path):
    cfg = config(tmp_path)
    cfg["models"][0]["helpers"] = {"hull2": [0, 0.9, 0.2]}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert close(m.bone_matrix(vi.bone_index(m, "hull2"))[1], (0, 0.9 * 3.2 / 1.2, 0.45))


def test_a_piece_selector_drops_the_connected_piece_at_a_point(tmp_path):
    cfg = config(tmp_path)
    cfg["models"][0]["drop"] = [{"piece_at": [0.05, -0.2, 0.85]}]  # a corner of the gun box
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    sm = vi.bone_submeshes(m, vi.bone_index(m, "turret_mesh"))[0]
    assert len(xbg.strip_triangles(sm.strip)) == 1  # nothing left: the placeholder


def test_a_model_s_own_texture_settings_make_its_own_atlas(tmp_path):
    cfg = config(tmp_path)
    vi.build(cfg, tmp_path)
    df = tmp_path / "mod" / "levels" / "L1" / "l1" / "w/gun/gun_df.xbt"
    plain = Image.open(io.BytesIO(xbt.to_dds(df.read_bytes()))).convert("RGB").getpixel((5, 5))
    cfg["models"][0]["texture"] = {"gain": 2.0}
    vi.build(cfg, tmp_path)
    bright = Image.open(io.BytesIO(xbt.to_dds(df.read_bytes()))).convert("RGB").getpixel((5, 5))
    assert sum(bright) > 1.5 * sum(plain)


def test_clear_leaves_out_what_comes_near_a_seat_and_what_that_cuts_off(tmp_path):
    cfg = config(tmp_path)
    cfg["models"][0]["clear"] = {"around": ["hull2"], "radius": 0.35, "bones": ["hull2"]}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    # the hull box's floor passes 0.28 m under the hull2 bone: the cut takes it, and the rest of that small
    # piece goes with it (it would float): only the placeholder is left
    sm = vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0]
    assert len(xbg.strip_triangles(sm.strip)) == 1
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "Wheel1"))[0].strip)) == 12


def test_orbit_clears_round_the_circle_the_head_turns_on(tmp_path):
    cfg = config(tmp_path)
    # the hull2 bone (0, 0, 1) stands in for an eye inside the hull box (x within 1.33, floor 0.28 m under it):
    # 0.2 m round it reaches no wall; turned 1.2 m round it, the camera comes within 0.13 m of the side walls
    cfg["models"][0]["clear"] = {"around": ["hull2"], "radius": 0.2, "bones": ["hull2"]}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0].strip)) == 12  # the box, whole
    cfg["models"][0]["clear"]["orbit"] = 1.2
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0].strip)) == 1  # placeholder
    points = vi.orbits([(0.0, 0.0, 1.0)], 0.28, steps=8)
    assert len(points) == 9 and points[0] == (0.0, 0.0, 1.0)
    assert all(abs(math.hypot(x, y) - 0.28) < 1e-9 and z == 1.0 for x, y, z in points[1:])


def test_floor_keeps_what_lies_below_the_eye(tmp_path):
    cfg = config(tmp_path)
    # the hull box's floor passes 0.28 m under the hull2 bone (the eye): within 0.35 m, but below a floor of 0.2
    cfg["models"][0]["clear"] = {"around": ["hull2"], "radius": 0.35, "bones": ["hull2"], "floor": 0.2}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0].strip)) == 12  # kept
    cfg["models"][0]["clear"]["floor"] = 0.3
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0].strip)) == 1  # placeholder
    assert vi.above(((0, 0, 0), (1, 0, 1), (0, 1, 1)), 0.5) and not vi.above(((0, 0, 0), (1, 0, 0), (0, 1, 0)), 0.5)


def test_helpers_move_by_metres_and_the_clearance_follows(tmp_path):
    cfg = config(tmp_path)
    # the eye (hull2 bone, 0.28 m over the box's floor) moved 0.15 m down: 0.2 m round it now reaches the floor
    cfg["models"][0]["clear"] = {"around": ["hull2"], "radius": 0.2, "bones": ["hull2"]}
    cfg["models"][0]["helpers"] = {"hull2": {"by": [0, 0, -0.15]}}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert close(m.bone_matrix(vi.bone_index(m, "hull2"))[1], (0, 0, 0.85))
    assert len(xbg.strip_triangles(vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0].strip)) == 1
    cfg["models"][0]["helpers"] = {"hull2": {"at": [0, 0.5, 1.2]}}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    assert close(m.bone_matrix(vi.bone_index(m, "hull2"))[1], (0, 0.5, 1.2))


def test_point_triangle_distance():
    a, b, c = (0, 0, 0), (1, 0, 0), (0, 1, 0)
    assert abs(vi.point_triangle((0.2, 0.2, 0.5), a, b, c) - 0.5) < 1e-9  # above the face
    assert abs(vi.point_triangle((2, 0, 0), a, b, c) - 1.0) < 1e-9  # past a corner
    assert abs(vi.point_triangle((0.5, -1, 0), a, b, c) - 1.0) < 1e-9  # beside an edge


def test_inner_gives_the_shell_a_lit_inside(tmp_path):
    cfg = config(tmp_path)
    cfg["models"][0]["parts"][-1]["inner"] = {"offset": 0.01, "up": 1.2}
    vi.build(cfg, tmp_path)
    m = built(tmp_path)
    sm = vi.bone_submeshes(m, vi.bone_index(m, "hull2"))[0]
    assert len(xbg.strip_triangles(sm.strip)) == 24  # the box's 12 and their insides
    rot, _ = m.bone_matrix(vi.bone_index(m, "hull2"))
    ups = [xbg.mat_vec(rot, v["normal"])[2] for v in sm.vertices]
    assert sum(u > 0.3 for u in ups) > len(ups) / 2  # the insides of the walls and the roof face up


def test_lower_brings_walls_beside_a_seat_down(tmp_path):
    cfg = config(tmp_path)
    # Wheel1's bone stands in for a seat: (-0.85, 1.6, 0.45); the hull's corners beside it, outboard, go down
    cfg["models"][0]["lower"] = {
        "around": ["Wheel1"],
        "below": -1.0,
        "reach": 5.0,
        "outboard": -5.0,
        "bones": ["hull2"],
    }
    vi.build(cfg, tmp_path)
    lo, hi = vi.box_of(placed_points(built(tmp_path), "hull2"))
    assert abs(hi[2] - (0.45 + 1.0)) < 1e-3  # no higher than 1.0 above that "eye"
