"""tools/blood_recolor.py on synthetic textures, particle libraries and archives (no game data)"""

import json
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import blood_recolor as br  # noqa: E402
import dat2  # noqa: E402
import xbt  # noqa: E402

RED = [142, 25, 16]
BLUE = br.Colour({"from": RED, "to": [92, 78, 240]})
GREEN = br.Colour({"from": RED, "to": [186, 204, 104]})


def palette(c0, c1, four):
    """a DXT colour block's four entries (RGB 0..255, None for transparent black)"""
    a, b = br.unpack565(c0), br.unpack565(c1)
    if four:
        return [a, b, tuple((2 * x + y) / 3 for x, y in zip(a, b)), tuple((x + 2 * y) / 3 for x, y in zip(a, b))]
    return [a, b, tuple((x + y) / 2 for x, y in zip(a, b)), None]


def texels(block, at, dxt1):
    c0, c1, idx = struct.unpack_from("<HHI", block, at)
    pal = palette(c0, c1, not dxt1 or c0 > c1)
    return [pal[(idx >> (2 * k)) & 3] for k in range(16)]


def close(a, b, tol):
    if a is None or b is None:
        return a is b
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_colour_takes_from_to_to_and_keeps_greys():
    assert close(BLUE.apply(RED), (92, 78, 240), 1e-9)
    for v in (0, 40, 128, 255):
        assert close(BLUE.apply((v, v, v)), (v, v, v), 1e-9)


def test_colour_is_linear_so_dxt_endpoints_can_carry_it():
    a, b = (120, 30, 20), (40, 10, 12)
    mid = tuple((2 * x + y) / 3 for x, y in zip(a, b))
    lerp = tuple((2 * x + y) / 3 for x, y in zip(BLUE.apply(a), BLUE.apply(b)))
    assert close(BLUE.apply(mid), lerp, 1e-9)


def test_colour_refuses_a_from_that_is_not_red():
    with pytest.raises(SystemExit):
        br.Colour({"from": [20, 100, 30], "to": [1, 2, 3]})


@pytest.mark.parametrize("dxt1", [True, False])
def test_block_texels_follow_the_map_when_the_order_turns(dxt1):
    # a pure red over a greyer red: c0 > c1 (four colours); mapped to blue the grey one has more red
    c0, c1 = br.pack565((100, 0, 0)), br.pack565((90, 60, 60))
    assert c0 > c1
    n0, n1 = (br.pack565(BLUE.apply(br.unpack565(c))) for c in (c0, c1))
    assert n0 < n1  # the case the swap is for
    idx = sum(((k * 7 + k // 3) % 4) << (2 * k) for k in range(16))
    block = struct.pack("<HHI", c0, c1, idx)
    out = br.recolour_block(block, 0, BLUE, four_colour_always=not dxt1)
    o0, o1, _ = struct.unpack_from("<HHI", out, 0)
    assert o0 > o1  # the order (DXT1's mode) is the original's
    for before, after in zip(texels(block, 0, dxt1), texels(out, 0, dxt1)):
        assert close(after, BLUE.apply(before), 10)


def test_dxt1_three_colour_block_keeps_its_transparent_texels():
    c0, c1 = br.pack565((60, 12, 10)), br.pack565((120, 24, 18))  # dark enough not to clip
    assert c0 < c1
    idx = sum((k % 4) << (2 * k) for k in range(16))
    block = struct.pack("<HHI", c0, c1, idx)
    out = br.recolour_block(block, 0, GREEN, four_colour_always=False)
    o0, o1, _ = struct.unpack_from("<HHI", out, 0)
    assert o0 <= o1
    for before, after in zip(texels(block, 0, True), texels(out, 0, True)):
        assert (before is None) == (after is None)
        assert before is None or close(after, GREEN.apply(before), 10)


def test_endpoints_that_meet_after_the_map_read_one_colour():
    # two reds the map puts on one 565 value: all texels must read that value in either mode
    c0, c1 = br.pack565((200, 0, 0)), br.pack565((192, 0, 0))
    flat = br.Colour({"from": [255, 0, 0], "to": [0, 0, 0]})
    out = br.recolour_block(struct.pack("<HHI", c0, c1, 0xFFFFFFFF), 0, flat, four_colour_always=True)
    o0, o1, idx = struct.unpack_from("<HHI", out, 0)
    assert o0 == o1 and idx == 0


def texture(fmt, w, h, mips):
    """an .xbt whose colour endpoints are reds and whose alpha bytes count up"""
    out = bytearray()
    for level in range(mips):
        for k in range(xbt.level_size(fmt, w, h, level) // br.BLOCK[fmt]):
            if fmt != br.DXT1:
                out += bytes((k + i) % 256 for i in range(8))
            out += struct.pack("<HHI", br.pack565((180, 30 + k % 9, 20)), br.pack565((50, 8, 6)), 0x1B1B1B1B)
    return xbt.MAGIC + struct.pack("<7I", w, h, len(out), fmt, mips, 1, 0) + bytes(out)


@pytest.mark.parametrize("fmt", [br.DXT1, br.DXT3, br.DXT5])
def test_xbt_keeps_header_size_and_alpha(fmt):
    t = texture(fmt, 16, 8, 3)
    out = br.recolour_xbt(t, BLUE)
    assert out[:32] == t[:32] and len(out) == len(t)
    if fmt != br.DXT1:
        for p in range(32, len(t), 16):
            assert out[p : p + 8] == t[p : p + 8]
    first = struct.unpack_from("<H", out, 32 + br.COLOUR_AT[fmt])[0]
    r, g, b = br.unpack565(first)
    assert b > r and b > g  # blue now


def test_xbt_refuses_uncompressed_textures():
    t = xbt.MAGIC + struct.pack("<7I", 4, 4, 64, 0x0C, 1, 1, 0) + bytes(64)
    with pytest.raises(SystemExit):
        br.recolour_xbt(t, BLUE)


LIBRARY = (
    b'<?xml version="1.0" encoding="ISO-8859-1" ?>\r\n<ParticleLibrary>\r\n'
    b'    <Particles Name="Other_Lib.Other_A">\r\n'
    b'        <Params Active="1" EndColor="0.258824,0,0" StartColor="0.258824,0,0" Texture="x" />\r\n'
    b"    </Particles>\r\n"
    b'    <Particles Name="GFX_Explosions_Sapper.GFX_Explosions_Sapper_Smoke">\r\n'
    b'        <Params Active="1" EndColor="0.592157,0,0" SelfIllumColor="0.5,0,0" StartColor="0.258824,0,0" />\r\n'
    b'        <Params Active="1" EndColor="0.901961,0.486275,0.184314" StartColor="1,1,1" />\r\n'
    b"        <Childs />\r\n"
    b"    </Particles>\r\n"
    b'    <Particles Name="GFX_Explosions_Sapper_Water">\r\n'
    b'        <Params Active="0" EndColor="0.392157,0,0" StartColor="0.392157,0,0" />\r\n'
    b"    </Particles>\r\n"
    b'    <Particles Name="Next_Lib.Next_A">\r\n'
    b'        <Params Active="1" EndColor="0.392157,0,0" StartColor="0.392157,0,0" />\r\n'
    b"    </Particles>\r\n</ParticleLibrary>\r\n"
)


def test_tints_change_only_the_named_librarys_reddish_colours():
    out, changes = br.recolour_tints(LIBRARY, {"GFX_Explosions_Sapper"}, GREEN)
    assert len(changes) == 4  # the smoke's start and end, the water's start and end (its library's 2nd effect)
    a, b = LIBRARY.split(b"\r\n"), out.split(b"\r\n")
    assert len(a) == len(b)
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert changed == [6, 11]
    assert b'SelfIllumColor="0.5,0,0"' in b[6] and b'StartColor="1,1,1"' in b[7]
    g = tuple(float(x) for x in b[6].split(b'StartColor="')[1].split(b'"')[0].split(b","))
    assert close(g, br.tint((0.258824, 0, 0), GREEN), 1e-5) and g[1] > g[0] > g[2]


BLOODLIB = (
    b'<?xml version="1.0" encoding="ISO-8859-1" ?>\r\n<ParticleLibrary>\r\n'
    b'    <Particles Name="GFX_Particle_Bullet_Hit_Blood_Big.GFX_Particle_Bullet_Hit_Blood_Big_A">\r\n'
    b'        <Params Active="1" Count="5" LifeTime="0.5" Size="0.1" SizeSpeed="0.12" Speed="40" '
    b'Texture="\\Magma\\Textures\\Hud\\damage_21.XBT" />\r\n'
    b'        <Params Active="0" Count="0" LifeTime="1" Size="1" SizeSpeed="0" Speed="2" Texture="" />\r\n'
    b"        <Childs>\r\n"
    b'            <Particles Name="GFX_Particle_Bullet_Hit_Blood_Big_C">\r\n'
    b'                <Params Active="1" Count="1" LifeTime="0.35" Size="0" SizeSpeed="0.05" Speed="0.5" '
    b'Texture="\\Magma\\Textures\\Hud\\damage_21.XBT" />\r\n'
    b"            </Particles>\r\n"
    b'            <Particles Name="GFX_Particle_Bullet_Hit_Blood_Big_Sprite">\r\n'
    b'                <Params Active="1" Count="1" LifeTime="0.1" Size="100" SizeSpeed="0.1" Speed="20" '
    b'Texture="Textures_xbox\\Sprites\\GFX_Sparks_A.xbt" />\r\n'
    b"            </Particles>\r\n"
    b"        </Childs>\r\n"
    b"    </Particles>\r\n"
    b'    <Particles Name="GFX_Particle_Bullet_Hit_Concrete.GFX_Particle_Bullet_Hit_Concrete_A">\r\n'
    b'        <Params Active="1" Count="2" LifeTime="1" Size="0.25" SizeSpeed="0.75" Speed="4" '
    b'Texture="\\Magma\\Textures\\Hud\\damage_21.XBT" />\r\n'
    b"    </Particles>\r\n</ParticleLibrary>\r\n"
)
SPRAYED = {
    "libraries": ["GFX_Particle_Bullet_Hit_Blood_Big"],
    "texture": "damage_21",
    "size": 2.5,
    "count": 2,
    "speed": 1.3,
    "life": 1.4,
}


def test_spray_scales_the_blood_emitters_only():
    out, changes = br.edit_particles(BLOODLIB, spray=SPRAYED)
    a, b = BLOODLIB.split(b"\r\n"), out.split(b"\r\n")
    assert len(a) == len(b)
    assert [i for i, (x, y) in enumerate(zip(a, b)) if x != y] == [3, 7]  # A's and C's emitters
    assert b'Count="10" LifeTime="0.7" Size="0.25" SizeSpeed="0.3" Speed="52"' in b[3]
    assert b'Count="2" LifeTime="0.49" Size="0" SizeSpeed="0.125" Speed="0.65"' in b[7]
    assert len(changes) == 10
    # the sparks (another texture), the inactive emitter and other libraries stay
    assert b[4] == a[4] and b[10] == a[10] and b[15] == a[15]


def test_spray_and_tints_in_one_pass():
    xml = LIBRARY.replace(
        b"</ParticleLibrary>",
        BLOODLIB.split(b"<ParticleLibrary>\r\n")[1].split(b"</ParticleLibrary>")[0] + b"</ParticleLibrary>",
    )
    out, changes = br.edit_particles(xml, {"GFX_Explosions_Sapper": GREEN}, SPRAYED)
    assert len(changes) == 4 + 10
    assert out == br.edit_particles(br.recolour_tints(xml, {"GFX_Explosions_Sapper"}, GREEN)[0], spray=SPRAYED)[0]


def materials(decals):
    out = bytearray(b"FTAM" + struct.pack("<II", 1, len(decals)))
    for i, d in enumerate(decals):
        e = bytearray(br.ENTRY)
        struct.pack_into("<iii", e, 0, i, 0, 0)
        struct.pack_into("<if", e, 0xC, d, 0.025)
        struct.pack_into("<f", e, 0x60, 0.125)
        out += e
    return bytes(out)


def test_stains_resize_the_flesh_decal_of_the_named_materials():
    b = materials([1, 6, 6, 7])
    out = br.resize_stains(b, [1, 2], 0.4, 0.1)
    assert len(out) == len(b)
    for i, size, var in ((0, 0.025, 0.125), (1, 0.4, 0.1), (2, 0.4, 0.1), (3, 0.025, 0.125)):
        at = 12 + i * br.ENTRY
        assert struct.unpack_from("<f", out, at + 0x10)[0] == pytest.approx(size)
        assert struct.unpack_from("<f", out, at + 0x60)[0] == pytest.approx(var)
    assert out[:12] == b[:12]
    with pytest.raises(SystemExit, match="flesh decal"):
        br.resize_stains(b, [3], 0.4, 0.1)
    with pytest.raises(SystemExit, match="material list"):
        br.resize_stains(b[:-1], [1], 0.4, 0.1)


def level_archive(game, level, files):
    folder = game / "levels" / level
    folder.mkdir(parents=True, exist_ok=True)
    dat, fat = dat2.build({dat2.name_hash(p): b for p, b in files.items()})
    (folder / f"{level.lower()}.dat").write_bytes(dat)
    (folder / f"{level.lower()}.fat").write_bytes(fat)


SPRAY = "magma/textures/hud/damage_21.xbt"
DECAL = "textures_xbox/decal/gfx_decal_bullet_hit_flesh_a.xbt"
SPLAT = "textures_xbox/decal/gfx_decal_explosion_bloodsplat_df.xbt"
MATS = "particles/materials.dat"


def setup(tmp_path, mods, **top):
    game = tmp_path / "game"
    marsh = LIBRARY.replace(b"</ParticleLibrary>", BLOODLIB.split(b"<ParticleLibrary>\r\n")[1])
    level_archive(
        game,
        "01_Beach",
        {
            SPRAY: texture(br.DXT3, 8, 8, 1),
            DECAL: texture(br.DXT5, 8, 8, 2),
            MATS: materials([6, 6]),
            "levels/01_Beach/01_Beach_DepLoadParticles.xml": BLOODLIB,
        },
    )
    level_archive(
        game,
        "10_Marsh",
        {
            SPRAY: texture(br.DXT3, 8, 8, 1),
            DECAL: texture(br.DXT5, 8, 8, 2),
            SPLAT: texture(br.DXT5, 16, 16, 3),
            MATS: materials([6, 6]),
            "levels/10_Marsh/10_Marsh_DepLoadParticles.xml": marsh,
        },
    )
    level_archive(game, "M01_Multi", {SPRAY: texture(br.DXT3, 8, 8, 1)})
    cfg = {
        "game": "game",
        "archives": ["levels/[0-9]*"],
        "out": "mods",
        "group": "Halo: effects",
        "colours": {"elite": {"from": RED, "to": [92, 78, 240]}, "flood": {"from": RED, "to": [186, 204, 104]}},
        "textures": [SPRAY, DECAL],
        **top,
        "mods": mods,
    }
    path = tmp_path / "blood.json"
    path.write_text(json.dumps(cfg))
    return path


STAINS = {
    "materials": [0, 1],
    "size": 0.4,
    "variance": 0.1,
    "texture": DECAL,
    "splat": {"game": "game", "archive": "levels/10_Marsh/10_marsh", "path": SPLAT},
}


def test_build_writes_alternatives_and_a_separate_set(tmp_path, capsys):
    path = setup(
        tmp_path,
        {
            "halo-blood-elite": {"colour": "elite", "name": "Elite"},
            "halo-blood-flood": {"colour": "flood", "name": "Flood", "levels": {"levels/10_*": "elite"}},
            "halo-blood-red": {"colour": None, "tints": None},
            "halo-blood-sappers": {
                "set": "sapper",
                "colour": "flood",
                "archives": ["levels/10_*"],
                "textures": [SPLAT],
                "spray": None,
                "stains": None,
                "tints": None,
            },
        },
        spray=SPRAYED,
        stains=STAINS,
        tints={"GFX_Explosions_Sapper": "flood"},
    )
    planned = br.build(path, check=tmp_path / "check")
    mods = tmp_path / "mods"
    beach, marsh = "levels/01_Beach/01_beach/", "levels/10_Marsh/10_marsh/"
    beach_lib, marsh_lib = (
        "levels/01_Beach/01_Beach_DepLoadParticles.xml",
        "levels/10_Marsh/10_Marsh_DepLoadParticles.xml",
    )
    elite = mods / "halo-blood-elite"
    files = set((elite / ".files").read_text().split())
    assert files == {a + f for a in (beach, marsh) for f in (SPRAY, DECAL, MATS)} | {
        beach + beach_lib,
        marsh + marsh_lib,
    }  # not the multiplayer map
    assert "group = Halo: effects" in (elite / "mod.ini").read_text()
    splat = texture(br.DXT5, 16, 16, 3)
    # the hit decal is the splat, recoloured; the materials are resized; sprays scaled; the sapper tinted flood
    assert (elite / beach / DECAL).read_bytes() == br.recolour_xbt(splat, BLUE)
    assert (elite / beach / MATS).read_bytes() == br.resize_stains(materials([6, 6]), [0, 1], 0.4, 0.1)
    assert (elite / beach / beach_lib).read_bytes() == br.edit_particles(BLOODLIB, spray=SPRAYED)[0]
    marsh_xml = (elite / marsh / marsh_lib).read_bytes()
    marsh_src = LIBRARY.replace(b"</ParticleLibrary>", BLOODLIB.split(b"<ParticleLibrary>\r\n")[1])
    assert marsh_xml == br.edit_particles(marsh_src, {"GFX_Explosions_Sapper": GREEN}, SPRAYED)[0]
    flood = mods / "halo-blood-flood"
    spray = lambda mod, level: (mod / level / SPRAY).read_bytes()
    # per-archive colour: the Marsh's spray is the elite's in the flood mod too
    assert spray(flood, marsh) == spray(elite, marsh)
    assert spray(flood, beach) != spray(elite, beach)
    # red: nothing recoloured, the splat as it is, no tints
    red = mods / "halo-blood-red"
    assert not (red / beach / SPRAY).exists()
    assert (red / beach / DECAL).read_bytes() == splat
    assert (red / marsh / marsh_lib).read_bytes() == br.edit_particles(marsh_src, spray=SPRAYED)[0]
    sappers = mods / "halo-blood-sappers"
    assert set((sappers / ".files").read_text().split()) == {marsh + SPLAT}
    assert len(planned["halo-blood-sappers"]) == 1
    out = capsys.readouterr().out
    assert "halo-blood-elite: 8 files in 2 archives" in out and "2 StartColor" in out and "2 stains" in out
    assert (tmp_path / "check" / "blood-mods.png").exists()

    # a rebuild without the decal's splat takes the splat out
    cfg = json.loads(path.read_text())
    cfg["stains"] = None
    cfg["textures"] = [SPRAY]
    path.write_text(json.dumps(cfg))
    br.build(path, ["halo-blood-elite"])
    assert not (elite / beach / DECAL).exists() and not (elite / beach / MATS).exists()
    assert (elite / beach / SPRAY).exists()


def test_mods_of_other_sets_that_share_files_are_refused(tmp_path):
    path = setup(
        tmp_path,
        {
            "halo-blood-elite": {"colour": "elite"},
            "halo-blood-spray": {"colour": "flood", "textures": [SPRAY]},  # same set: an alternative
        },
    )
    br.build(path, dry_run=True)
    path = setup(
        tmp_path,
        {
            "halo-blood-elite": {"colour": "elite"},
            "halo-blood-other": {"set": "other", "colour": "flood", "textures": [SPRAY]},
        },
    )
    with pytest.raises(SystemExit, match="not alternatives"):
        br.build(path, dry_run=True)


def test_unknown_colour_and_empty_mod_are_refused(tmp_path):
    with pytest.raises(SystemExit, match="no colour"):
        br.build(setup(tmp_path, {"m": {"colour": "grunt"}}), dry_run=True)
    with pytest.raises(SystemExit, match="no colour"):
        br.build(setup(tmp_path, {"m": {"colour": "elite", "tints": {"X": "grunt"}}}), dry_run=True)
    with pytest.raises(SystemExit, match="writes nothing"):
        br.build(setup(tmp_path, {"m": {"colour": "elite", "textures": ["no/such.xbt"]}}), dry_run=True)
