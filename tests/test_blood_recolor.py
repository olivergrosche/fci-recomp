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


def level_archive(game, level, files):
    folder = game / "levels" / level
    folder.mkdir(parents=True, exist_ok=True)
    dat, fat = dat2.build({dat2.name_hash(p): b for p, b in files.items()})
    (folder / f"{level.lower()}.dat").write_bytes(dat)
    (folder / f"{level.lower()}.fat").write_bytes(fat)


SPRAY = "magma/textures/hud/damage_21.xbt"
DECAL = "textures_xbox/decal/gfx_decal_bullet_hit_flesh_a.xbt"
SPLAT = "textures_xbox/decal/gfx_decal_explosion_bloodsplat_df.xbt"


def setup(tmp_path, mods):
    game = tmp_path / "game"
    level_archive(game, "01_Beach", {SPRAY: texture(br.DXT3, 8, 8, 1), DECAL: texture(br.DXT5, 8, 8, 2)})
    level_archive(
        game,
        "10_Marsh",
        {
            SPRAY: texture(br.DXT3, 8, 8, 1),
            SPLAT: texture(br.DXT5, 8, 8, 2),
            "levels/10_Marsh/10_Marsh_DepLoadParticles.xml": LIBRARY,
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
        "mods": mods,
    }
    path = tmp_path / "blood.json"
    path.write_text(json.dumps(cfg))
    return path


def test_build_writes_alternatives_and_a_separate_mod(tmp_path, capsys):
    path = setup(
        tmp_path,
        {
            "halo-blood-elite": {"colour": "elite", "name": "Elite"},
            "halo-blood-flood": {"colour": "flood", "name": "Flood", "levels": {"levels/10_*": "elite"}},
            "halo-blood-sappers": {
                "colour": "flood",
                "archives": ["levels/10_*"],
                "textures": [SPLAT],
                "particles": ["GFX_Explosions_Sapper"],
            },
        },
    )
    planned = br.build(path, check=tmp_path / "check")
    mods = tmp_path / "mods"
    elite = mods / "halo-blood-elite"
    assert sorted((elite / ".files").read_text().split()) == sorted(
        [
            "levels/01_Beach/01_beach/" + DECAL,
            "levels/01_Beach/01_beach/" + SPRAY,
            "levels/10_Marsh/10_marsh/" + SPRAY,
        ]
    )  # not the multiplayer map
    assert "group = Halo: effects" in (elite / "mod.ini").read_text()
    flood = mods / "halo-blood-flood"
    spray = lambda mod, level: (mod / level / SPRAY).read_bytes()
    # per-archive colour: the Marsh's spray is the elite's in the flood mod too
    assert spray(flood, "levels/10_Marsh/10_marsh") == spray(elite, "levels/10_Marsh/10_marsh")
    assert spray(flood, "levels/01_Beach/01_beach") != spray(elite, "levels/01_Beach/01_beach")
    sappers = mods / "halo-blood-sappers"
    xml = sappers / "levels/10_Marsh/10_marsh/levels/10_Marsh/10_Marsh_DepLoadParticles.xml"
    assert xml.read_bytes() == br.recolour_tints(LIBRARY, {"GFX_Explosions_Sapper"}, GREEN)[0]
    assert len(planned["halo-blood-sappers"]) == 2
    assert "4 particle tints" in capsys.readouterr().out
    assert (tmp_path / "check" / "blood-mods.png").exists()

    # a rebuild without the decal takes it out of the folders
    cfg = json.loads(path.read_text())
    cfg["textures"] = [SPRAY]
    path.write_text(json.dumps(cfg))
    br.build(path, ["halo-blood-elite"])
    assert not (elite / "levels/01_Beach/01_beach" / DECAL).exists()
    assert (elite / "levels/01_Beach/01_beach" / SPRAY).exists()


def test_mods_that_share_some_files_are_refused(tmp_path):
    path = setup(
        tmp_path,
        {
            "halo-blood-elite": {"colour": "elite"},
            "halo-blood-spray": {"colour": "flood", "textures": [SPRAY]},
        },
    )
    with pytest.raises(SystemExit, match="not alternatives"):
        br.build(path, dry_run=True)


def test_unknown_colour_and_empty_mod_are_refused(tmp_path):
    with pytest.raises(SystemExit, match="no colour"):
        br.build(setup(tmp_path, {"m": {"colour": "grunt"}}), dry_run=True)
    with pytest.raises(SystemExit, match="writes nothing"):
        br.build(setup(tmp_path, {"m": {"colour": "elite", "textures": ["no/such.xbt"]}}), dry_run=True)
