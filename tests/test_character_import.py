"""tools/character_import.py on a synthetic skinned glTF and synthetic models (no game or Halo data)"""

import base64
import json
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import character_import as ci  # noqa: E402
from test_xbg import close, skinned_template, template  # noqa: E402
import xbg  # noqa: E402
import xbt  # noqa: E402

# The source: joints Bone1 -> Bone2 -> Extra -> Bone3 along the glTF's x (0.5, 0.1, 0.1 apart), no
# rotations. The template (test_xbg.skinned_template) has Bone1 -> Bone2 -> Bone3 0.1 apart along -y of the
# model from (0, 0, 1), Bone3 turned back to the model's axes, Bone4 ... on along +x.
JOINTS = (
    ("Bone1", None, (0.0, 0.0, 0.0)),
    ("Bone2", 0, (0.5, 0.0, 0.0)),
    ("Extra", 1, (0.1, 0, 0)),
    ("Bone3", 2, (0.1, 0, 0)),
)
# vertices: position, joint weights (joint number, weight)
A = ((0.25, 0.0, 0.1), [(0, 1.0)])  # halfway along Bone1, 0.1 above it
B = ((0.65, 0.05, 0.0), [(2, 1.0)])  # on Extra (moves with Bone2), 0.05 to the side
C = ((0.7, 0.05, 0.0), [(3, 1.0)])  # at Bone3, 0.05 to the side
D = ((0.05, 0.0, 0.0), [(0, 0.5), (1, 0.5)])
E = ((0.6, 0.0, -0.2), [(3, 1.0)])  # Bone3's lowest point
VERTICES = (A, B, C, D, E)


def gltf(tmp_path, blend=True):
    """the source as a .gltf with an embedded buffer: one opaque primitive (A, B, C, D, E), and with blend a
    transparent one (one triangle) that the import leaves out by default"""
    n = len(VERTICES)
    blob = bytearray()
    views = []

    def put(data):
        views.append((len(blob), len(data)))
        blob.extend(data)
        blob.extend(bytes(-len(blob) % 4))

    put(b"".join(struct.pack("<3f", *p) for p, _ in VERTICES))
    put(b"".join(struct.pack("<3f", 0, 0, 1) for _ in VERTICES))
    put(b"".join(struct.pack("<2f", 0.25 * k, 0.5) for k in range(n)))
    put(b"".join(struct.pack("<4H", *([j for j, _ in s] + [0] * (4 - len(s)))) for _, s in VERTICES))
    put(b"".join(struct.pack("<4f", *([w for _, w in s] + [0.0] * (4 - len(s)))) for _, s in VERTICES))
    put(struct.pack("<9H", 0, 1, 2, 0, 2, 3, 2, 1, 4))
    put(struct.pack("<3H", 0, 1, 3))
    world = []
    for _, parent, pos in JOINTS:
        world.append(pos if parent is None else tuple(a + b for a, b in zip(world[parent], pos)))
    put(b"".join(struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1) for x, y, z in world))
    acc = [
        {"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3"},
        {"bufferView": 1, "componentType": 5126, "count": n, "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": n, "type": "VEC2"},
        {"bufferView": 3, "componentType": 5123, "count": n, "type": "VEC4"},
        {"bufferView": 4, "componentType": 5126, "count": n, "type": "VEC4"},
        {"bufferView": 5, "componentType": 5123, "count": 9, "type": "SCALAR"},
        {"bufferView": 6, "componentType": 5123, "count": 3, "type": "SCALAR"},
        {"bufferView": 7, "componentType": 5126, "count": len(JOINTS), "type": "MAT4"},
    ]
    attrs = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "JOINTS_0": 3, "WEIGHTS_0": 4}
    prims = [{"attributes": attrs, "indices": 5, "material": 0}]
    if blend:
        prims.append({"attributes": attrs, "indices": 6, "material": 1})
    nodes = []
    for k, (name, _, pos) in enumerate(JOINTS):
        nodes.append({"name": name, "translation": list(pos)})
        if k + 1 < len(JOINTS):
            nodes[-1]["children"] = [k + 1]
    nodes.append({"name": "body", "mesh": 0, "skin": 0})
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, len(JOINTS)]}],
        "nodes": nodes,
        "skins": [{"joints": list(range(len(JOINTS))), "inverseBindMatrices": 7}],
        "meshes": [{"primitives": prims}],
        "materials": [
            {"name": "skin", "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.25, 0.125, 1], "roughnessFactor": 0}},
            {"name": "glow", "alphaMode": "BLEND", "pbrMetallicRoughness": {"baseColorFactor": [0, 1, 0, 0.5]}},
        ],
        "buffers": [{"byteLength": len(blob), "uri": "data:;base64," + base64.b64encode(bytes(blob)).decode()}],
        "bufferViews": [{"buffer": 0, "byteOffset": o, "byteLength": s} for o, s in views],
        "accessors": acc,
    }
    path = tmp_path / "src.gltf"
    path.write_text(json.dumps(g))
    return path


def setup(tmp_path, cfg=None, bones=None):
    joints, prims, _ = ci.read_source(gltf(tmp_path), ["x", "y", "z"], 1.0)
    model = xbg.Model(skinned_template())
    direct = ci.bone_map(joints, model, bones)
    return joints, prims, model, direct, ci.Fit(joints, prims, model, direct, cfg)


def test_reads_joints_and_skinned_vertices(tmp_path):
    joints, prims, _ = ci.read_source(gltf(tmp_path), ["x", "y", "z"], 2.0)
    assert [j.name for j in joints] == ["Bone1", "Bone2", "Extra", "Bone3"]
    assert [j.parent for j in joints] == [None, 0, 1, 2]
    assert close(joints[3].at, (1.4, 0, 0)) and close(joints[3].axes[0], (1, 0, 0))
    assert close(prims[0]["pos"][0], (0.5, 0, 0.2)) and prims[0]["skin"][3] == [(0, 0.5), (1, 0.5)]
    assert prims[0]["tris"][:2] == [(0, 1, 2), (0, 2, 3)]


def test_axes_turn_joints_and_vertices(tmp_path):
    joints, prims, _ = ci.read_source(gltf(tmp_path), ["x", "-z", "y"], 1.0)  # glTF y up -> the game's z up
    assert close(prims[0]["pos"][0], (0.25, -0.1, 0.0)) and close(prims[0]["normal"][0], (0, -1, 0))
    assert close(joints[0].axes[2], (0, -1, 0)) and close(joints[0].axes[1], (0, 0, 1))


def test_names_match_without_case_spaces_or_underscores():
    assert ci.key("bip01 l upperarm") == ci.key("Bip01_L UpperArm") == "bip01 l upperarm"
    assert ci.key("Bip01_L  Forearm RollBone") == "bip01 l forearm rollbone"


def test_maps_by_name_and_merges_unmapped_joints_into_their_ancestor(tmp_path):
    joints, _, model, direct, fit = setup(tmp_path)
    names = [model.bones[direct[j]].name if j in direct else None for j in range(len(joints))]
    assert names == ["Bone1", "Bone2", None, "Bone3"]
    assert fit.owner == [0, 1, 1, 3]
    assert fit.chain == {0: 1, 1: 3, 3: None}
    assert fit.mode == {0: "align", 1: "align", 3: "frame"}


def test_bone_overrides(tmp_path):
    joints, _, model, direct, _ = setup(tmp_path, bones={"bone3": None, "extra": "Bone4"})
    assert {joints[j].name: model.bones[b].name for j, b in direct.items()} == {
        "Bone1": "Bone1",
        "Bone2": "Bone2",
        "Extra": "Bone4",
    }
    with pytest.raises(SystemExit, match="no skin matrix"):
        setup(tmp_path, bones={"bone1": "BIP01"})
    with pytest.raises(SystemExit, match="no such bone"):
        setup(tmp_path, bones={"bone1": "Nothing"})


def test_aligned_joints_fit_the_template_s_lengths(tmp_path):
    joints, prims, model, direct, fit = setup(tmp_path, {"thickness": 0.5, "ground": []})
    frames = model.frames()
    assert close((fit.ratio[0], fit.ratio[1]), (0.2, 0.5), 1e-6)  # 0.1 / 0.5, 0.1 / 0.2
    for j, b in direct.items():  # each joint lands on its bone
        assert close(fit.place(joints[j].at, [(j, 1.0)])[0], frames[b][1], 1e-6)
    p, n, skin = fit.vertex(A[0], (0, 0, 1), A[1])
    # halfway down the template's Bone1 (along -y), 0.1 above at thickness 0.5
    assert close(p, (0, -0.05, 1.05), 1e-6) and skin == [(1, 1.0)]
    assert close(n, (0, 0, 1), 1e-6)
    p, _, skin = fit.vertex(B[0], (0, 0, 1), B[1])  # 0.15 past Bone2 at half length; the side (+y) is +x
    assert close(p, (0.025, -0.175, 1.0), 1e-6) and skin == [(2, 1.0)]  # Extra's weight goes to Bone2


def test_frame_joints_carry_their_frame_onto_the_bone(tmp_path):
    _, _, model, _, fit = setup(tmp_path, {"thickness": 0.5, "ground": []})
    p, _, skin = fit.vertex(C[0], (0, 0, 1), C[1])
    rot, at = model.frames()[3]
    assert close(p, xbg.add(at, xbg.mat_vec(rot, (0, 0.025, 0))), 1e-6) and skin == [(3, 1.0)]


def test_keep_joints_keep_their_orientation_and_offset_moves_them(tmp_path):
    _, _, model, _, fit = setup(tmp_path, {"thickness": 1.0, "keep": ["Bone3"], "offset": {"Bone3": [0, 0, 0.1]}})
    at = model.frames()[3][1]
    p, _, _ = fit.vertex(C[0], (0, 0, 1), C[1])
    assert close(p, xbg.add(at, (0, 0.05, 0.1)), 1e-6)
    assert fit.mode[3] == "keep"


def test_ground_puts_the_lowest_vertex_on_the_floor_and_the_parent_stretches(tmp_path):
    joints, _, model, _, fit = setup(tmp_path, {"thickness": 1.0, "keep": ["Bone3"], "ground": ["Bone3"], "floor": 0.5})
    p, _, _ = fit.vertex(E[0], (0, 0, 1), E[1])
    assert close((p[2], fit.ground[3]), (0.5, -0.3), 1e-6)  # Bone3 at 1.0, E 0.2 below it
    # Bone2 reaches from its bone to the raised Bone3
    assert close(fit.place(joints[3].at, [(1, 1.0)])[0], fit.target[3], 1e-6)


def test_weights_are_shared_with_bones_between(tmp_path):
    # Bone1 -> template Bone1, Bone2 -> template Bone3: template Bone2 lies between, halfway
    _, _, model, _, fit = setup(tmp_path, {"split": {}, "ground": []}, bones={"bone2": "Bone3", "bone3": None})
    assert fit.chain[0] == 1 and [s for _, s in fit.splits[0][3]] == [2]
    shares = lambda x: dict(fit.vertex((x, 0, 0), (0, 0, 1), [(0, 1.0)])[2])  # noqa: E731
    assert shares(0.05) == {1: 1.0} and shares(0.45) == {2: 1.0}
    half = shares(0.25)
    assert close((half[1], half[2]), (0.5, 0.5), 1e-6)


def test_split_bones_from_the_config_count_once(tmp_path):
    cfg = {"split": {"Bone1": ["Bone2"]}, "ground": []}
    _, _, _, _, fit = setup(tmp_path, cfg, bones={"bone2": "Bone3", "bone3": None})
    assert [s for _, s in fit.splits[0][3]] == [2]


def test_packing_keeps_sizes_and_prefers_the_smaller_texture():
    w, h, f, at, rects = ci.pack([(512, 256), (256, 256), (256, 256), (256, 256)], 1024)
    assert (w, h) == (1024, 512) and f > 0.85 and len(set(at)) == 4  # 1024 x 1024 at full size wastes half
    for (x, y), (rw, rh) in zip(at, rects):
        assert x + rw + 2 * ci.PAD <= w and y + rh + 2 * ci.PAD <= h
    assert ci.pack([(64, 64)], 1024)[:3] == (256, 128, 1.0)  # small: a smaller texture at full size


def test_soft_gain_rolls_off_instead_of_clipping():
    table = ci.soft(1.6)
    assert table[0] == 0 and table[100] == round(100 * 1.6)
    assert all(a <= b for a, b in zip(table, table[1:])) and table[255] < 255 and table[230] < table[255]


def test_material_image_gain_gloss_and_matte(tmp_path):
    g = ci.weapon_import.Gltf(gltf(tmp_path))
    g.g["materials"][0]["alphaMode"] = "MASK"
    im = ci.material_image(g, 0, gain=1.0, gloss=(100, 200), matte=(1, 2, 3))
    assert im.size == (16, 16) and im.getpixel((0, 0)) == (128, 64, 32, 200)  # roughness 0: full gloss
    g.g["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] = [1, 1, 1, 0.2]  # below the cut-off: holes
    assert ci.material_image(g, 0, matte=(1, 2, 3)).getpixel((3, 3))[:3] == (1, 2, 3)


def build_files(tmp_path):
    src = gltf(tmp_path)
    folder = tmp_path / "extract"
    (folder / "c").mkdir(parents=True)
    (folder / "c" / "body.xbg").write_bytes(skinned_template())
    (folder / "h").mkdir()
    (folder / "h" / "hat.xbg").write_bytes(template())
    cfg = {
        "template": "extract",
        "archives": ["levels/L1/l1", "levels/L2/l2"],
        "out": "mod",
        "mod": {"name": "Test", "group": "Halo", "credit": "nobody"},
        "axes": ["x", "y", "z"],
        "scale": 1.0,
        "fit": {"thickness": 0.5, "ground": []},
        "texture": {"size": 64},
        "hide": ["h/hat.xbg"],
        "models": [{"model": "c/body.xbg", "source": src.name, "material": 0}],
    }
    ci.build(cfg, tmp_path)
    return tmp_path / "mod"


def test_build_writes_the_mod_folder(tmp_path):
    out = build_files(tmp_path)
    assert (out / "mod.ini").read_text() == "name = Test\ngroup = Halo\ncredit = nobody\n"
    for rel in ("levels/L1/l1", "levels/L2/l2"):
        m = xbg.Model((out / rel / "c" / "body.xbg").read_bytes())
        body, logo = m.parts
        assert body.triangles == 3  # the transparent primitive is left out
        assert logo.triangles == 1 and m.submeshes[logo.first].stride == 32  # hidden: one triangle
        hidden = m.placed(m.submeshes[logo.first])
        assert all(close(v["pos"], hidden[0]["pos"], 1e-6) for v in hidden)  # of no area
        sms = m.submeshes[body.first : body.first + body.count]
        assert all(sm.material == 0 and sm.stride == 28 for sm in sms)
        placed = [v for sm in sms for v in m.placed(sm)]
        assert any(close(v["pos"], (0, -0.05, 1.05), 2e-4) for v in placed)  # vertex A
        assert all(abs(v["uv"][0] - 0.5) < 0.5 and abs(v["uv"][1] - 0.5) < 0.5 for v in placed)
        df = (out / rel / "c" / "body_df.xbt").read_bytes()
        assert xbt.header(df)[3] == ci.DXT5
        hat = xbg.Model((out / rel / "h" / "hat.xbg").read_bytes())
        assert all(len(xbg.strip_triangles(sm.strip)) == 1 for sm in hat.submeshes)
        assert all(close(v["pos"], (0, 0, 0)) for sm in hat.submeshes for v in sm.vertices)  # in its bone


def test_mesh_turns_the_winding_and_keeps_the_atlas_place(tmp_path):
    joints, prims, model, direct, fit = setup(tmp_path, {"ground": []})
    verts, tris = ci.conformed_mesh(prims, fit, {0: (0.5, 0.25, 0.5, 0.25)}, {0})
    assert len(verts) == 5 and tris == [(0, 2, 1), (0, 3, 2), (2, 4, 1)]  # glTF counter-clockwise, games' not
    assert close(verts[1]["uv"], (0.5 + 0.25 * 0.5, 0.25 + 0.5 * 0.25))
    for v in verts:
        assert close(v["normal"], (0, 0, 1), 1e-6) and abs(ci.dot(v["tangent"], v["binormal"])) < 1e-6


def test_scale_doubles_when_the_mesh_outgrows_16_bits():
    m = xbg.Model(skinned_template())
    assert ci.needed_scale(m, [{"pos": (0, 0, 1.5)}]) == m.scale
    assert ci.needed_scale(m, [{"pos": (0, 0, 3.5)}]) == 4 * m.scale  # 2.5 m from the root


def test_splits_skip_bones_without_a_skin_matrix(tmp_path):
    # BIP01 (no skin matrix, as some Trigens' roll bones) named as a split bone is left out
    cfg = {"split": {"Bone1": ["BIP01"]}, "ground": []}
    _, _, _, _, fit = setup(tmp_path, cfg, bones={"bone2": "Bone3", "bone3": None})
    assert [s for _, s in fit.splits[0][3]] == [2]


def test_stretch_stops_at_the_ends_of_a_joint(tmp_path):
    _, _, _, _, fit = setup(tmp_path, {"thickness": 0.5, "ground": []})
    # 0.1 past Bone1's child on Bone1 alone: 0.5 at its fitted 0.2, the rest at the thickness
    p, m = fit.place((0.6, 0.0, 0.0), [(0, 1.0)])
    assert close(p, (0, -0.15, 1), 1e-6) and close(xbg.mat_vec(m, (1, 0, 0)), (0, -0.5, 0), 1e-6)
    p, _ = fit.place((-0.1, 0.0, 0.0), [(0, 1.0)])  # behind its joint
    assert close(p, (0, 0.05, 1), 1e-6)


def test_rotation_and_merged_settings():
    assert close(ci.mat_vec(ci.rotation((1, 0, 0), 90), (0, 1, 0)), (0, 0, 1), 1e-9)
    assert close(ci.mat_vec(ci.rotation((0, 0, 2), -90), (1, 0, 0)), (0, -1, 0), 1e-9)
    a = {"fit": {"size": {"A": 1, "B": 2}, "thickness": 1}, "texture": {"size": 64}, "x": [1]}
    b = {"fit": {"size": {"B": 3}}, "x": [2]}
    assert ci.merged(a, None, b) == {
        "fit": {"size": {"A": 1, "B": 3}, "thickness": 1},
        "texture": {"size": 64},
        "x": [2],
    }
    assert a["fit"]["size"]["B"] == 2  # the layers stay as they were


def test_reshape_turns_the_chosen_vertices_about_the_pivot(tmp_path):
    joints, prims, g = ci.read_source(gltf(tmp_path), ["x", "y", "z"], 1.0)
    rule = {"joint": "bone3", "pivot": [0.7, 0, 0], "axis": [0, 0, 1], "angle": 90}
    ci.reshape(joints, prims, g, [rule])
    body = prims[0]
    assert close(body["pos"][2], (0.65, 0.0, 0.0), 1e-6) and close(body["pos"][4], (0.7, -0.1, -0.2), 1e-6)
    assert close(body["normal"][2], (0, 0, 1), 1e-6) and close(body["pos"][0], A[0], 1e-6)  # others stay
    joints, prims, g = ci.read_source(gltf(tmp_path), ["x", "y", "z"], 1.0)
    ci.reshape(joints, prims, g, [dict(rule, box=[[0.65, -1, -1], [1, 1, 1]], material="skin")])
    assert close(prims[0]["pos"][2], (0.65, 0.0, 0.0), 1e-6) and close(prims[0]["pos"][4], E[0], 1e-6)
    with pytest.raises(SystemExit, match="no vertex"):
        ci.reshape(joints, prims, g, [dict(rule, box=[[5, 5, 5], [6, 6, 6]])])


def test_new_joints_take_the_far_end_of_their_parent(tmp_path):
    joints, prims, _ = ci.read_source(gltf(tmp_path), ["x", "y", "z"], 1.0)
    bones = ci.add_joints(
        joints, prims, [{"name": "Fist", "parent": "bone1", "at": 0.22, "blend": 0.05, "bone": "Bone4"}]
    )
    assert bones == {"Fist": "Bone4"}
    fist = joints[-1]
    assert fist.name == "Fist" and fist.parent == 0 and close(fist.at, (0.22, 0, 0)) and fist.rot == joints[0].rot
    skin = prims[0]["skin"]
    assert close([w for _, w in skin[0]], [0.8, 0.2], 1e-9) and [j for j, _ in skin[0]] == [4, 0]  # A: 0.03 past
    assert skin[3] == [(0, 0.5), (1, 0.5)]  # D: before the cut
    with pytest.raises(SystemExit, match="lies past"):
        ci.add_joints(joints, prims, [{"name": "Far", "parent": "bone1", "at": 5.0}])


def with_bump(model_bytes, material, texture):
    b = bytearray(model_bytes)
    struct.pack_into("<i", b, xbg.Model(model_bytes).materials[material].at + 0x14, texture)
    return bytes(b)


def test_texture_slots_name_other_files_of_the_model():
    m = xbg.Model(skinned_template())
    assert ci.texture_slots(m, 0, {}) == (0, None)
    assert ci.texture_slots(m, 0, {"diffuse": "C/LOGO_DF.XBT"}) == (1, None)
    with pytest.raises(SystemExit, match="no texture"):
        ci.texture_slots(m, 0, {"diffuse": "c/other.xbt"})
    with pytest.raises(SystemExit, match="no bump"):
        ci.texture_slots(m, 0, {"bump": "c/logo_df.xbt"})
    bumped = xbg.Model(with_bump(skinned_template(), 0, 1))
    assert ci.texture_slots(bumped, 0, {}) == (0, 1)
    assert ci.texture_slots(bumped, 0, {"diffuse": "c/logo_df.xbt", "bump": "c/body_df.xbt"}) == (1, 0)
    with pytest.raises(SystemExit, match="two texture files"):
        ci.texture_slots(bumped, 0, {"diffuse": "c/logo_df.xbt"})
    moved = xbg.Model(ci.with_textures(bumped.b, 0, 1, 0)).materials[0]
    assert (moved.diffuse, moved.bump) == (1, 0)


def mods_config(tmp_path, extra=None):
    """a config of three mods: two alternatives for c/body.xbg, hats alone in L1"""
    src = gltf(tmp_path)
    folder = tmp_path / "extract"
    (folder / "c").mkdir(parents=True, exist_ok=True)
    (folder / "c" / "body.xbg").write_bytes(skinned_template())
    (folder / "c" / "other.xbg").write_bytes(skinned_template())
    (folder / "h").mkdir(exist_ok=True)
    (folder / "h" / "hat.xbg").write_bytes(template())
    model = {"model": "c/body.xbg", "material": 0}
    cfg = {
        "template": "extract",
        "archives": ["levels/L1/l1", "levels/L2/l2"],
        "axes": ["x", "y", "z"],
        "scale": 1.0,
        "texture": {"size": 64},
        "creatures": {
            "thin": {"source": src.name, "fit": {"thickness": 0.5, "ground": []}},
            "thick": {"source": src.name, "fit": {"thickness": 2.0, "ground": []}, "texture": {"gain": 1.5}},
        },
        "mods": [
            {"out": "mods/a-thin", "mod": {"name": "A"}, "models": [dict(model, creature="thin")]},
            {"out": "mods/a-thick", "mod": {"name": "B"}, "models": [dict(model, creature="thick")]},
            {"out": "mods/hats", "mod": {"name": "C"}, "archives": ["levels/L1/l1"], "hide": ["h/hat.xbg"]},
        ],
    }
    cfg["mods"] += extra or []
    return cfg


def test_one_config_builds_several_mods(tmp_path):
    cfg = mods_config(tmp_path)
    assert ci.model_config(ci.mod_configs(cfg)[1], cfg["mods"][1]["models"][0])["texture"] == {"size": 64, "gain": 1.5}
    ci.build(cfg, tmp_path)
    out = tmp_path / "mods"
    thin = xbg.Model((out / "a-thin/levels/L1/l1/c/body.xbg").read_bytes())
    thick = xbg.Model((out / "a-thick/levels/L2/l2/c/body.xbg").read_bytes())
    lift = lambda m: max(v["pos"][2] for sm in m.submeshes[:1] for v in m.placed(sm))  # noqa: E731
    assert lift(thick) > lift(thin)  # vertex A stands off its bone by the thickness
    assert (out / "a-thick/.files").read_text().split() == [
        f"levels/{a}/c/{f}" for a in ("L1/l1", "L2/l2") for f in ("body.xbg", "body_df.xbt")
    ]
    assert sorted(p.relative_to(out / "hats").as_posix() for p in (out / "hats").rglob("*") if p.is_file()) == [
        ".files",
        "levels/L1/l1/h/hat.xbg",
        "mod.ini",
    ]
    with pytest.raises(SystemExit, match="no mod nothing"):
        ci.build(cfg, tmp_path, only=["nothing"])


def test_mods_of_different_models_must_not_share_a_file(tmp_path):
    other = {"out": "mods/b", "models": [{"model": "c/other.xbg", "material": 0, "creature": "thin"}]}
    with pytest.raises(SystemExit, match="a-thin and b both write levels/L1/l1/c/body_df.xbt"):
        ci.build(mods_config(tmp_path, [other]), tmp_path)
    other["models"][0]["texture"] = {"diffuse": "c/logo_df.xbt"}  # its own file: no conflict
    ci.build(mods_config(tmp_path, [other]), tmp_path, only=["b"])
    m = xbg.Model((tmp_path / "mods/b/levels/L1/l1/c/other.xbg").read_bytes())
    assert m.materials[0].diffuse == 1 and (tmp_path / "mods/b/levels/L1/l1/c/logo_df.xbt").exists()
    assert not (tmp_path / "mods/a-thin").exists()  # only the mod named was built


def test_a_rebuild_removes_only_the_files_it_no_longer_writes(tmp_path):
    cfg = mods_config(tmp_path)
    ci.build(cfg, tmp_path, only=["a-thin"])
    mod = tmp_path / "mods/a-thin"
    (mod / "levels/L1/l1/c/mine.txt").write_text("not the importer's")
    cfg["mods"][0]["models"][0]["texture"] = {"diffuse": "c/logo_df.xbt"}
    ci.build(cfg, tmp_path, only=["a-thin"])
    assert not (mod / "levels/L1/l1/c/body_df.xbt").exists() and (mod / "levels/L1/l1/c/logo_df.xbt").exists()
    assert (mod / "levels/L1/l1/c/mine.txt").exists()
    assert "levels/L2/l2/c/logo_df.xbt" in (mod / ".files").read_text().split()
