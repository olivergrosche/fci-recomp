"""tools/lua_patch.py on synthetic weapon scripts (no game data): built here as the games' compiler lays them
out, run by a small interpreter of those instructions, patched, run again"""

import json
from pathlib import Path
import struct
import sys
import zlib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import lua_patch as lp  # noqa: E402

HEADER = b"\x1bLua" + bytes([0x41, 1, 4, 4, 4, 6, 8, 8, 10, 4]) + struct.pack("<f", 314159265.0)
OP = lp.OP
WEAPON = {
    "name": "Blaster",
    "FPModel": "blaster.xbg",
    "eGroup": ("global", "EWeaponGroup_Secondary"),
    "FireParams": [
        {
            "damage": 8,
            "fire_rate": 0.2,
            "BulletTrail": {"colorA": [1, 1, 1], "speed": 60, "width": 0.05, "texture": "tracer.xbt"},
            "MuzzleParticle": {"effect": "GFX_Flash", "bulletCases": "GFX_Cases"},
        },
        {"damage": 0, "MuzzleParticle": {"effect": "GFX_Flash2"}},
    ],
}


class Compiler:
    """a main function that builds a table into a global, as the games' scripts do"""

    def __init__(self):
        self.k, self.code, self.top = [], [], 0

    def const(self, v):
        entry = (
            (lp.STRING, v.encode() + b"\0")
            if isinstance(v, str)
            else (lp.NUMBER, struct.unpack("<f", struct.pack("<f", v))[0])
        )
        if entry not in self.k:
            self.k.append(entry)
        return self.k.index(entry)

    def value(self, reg, v):
        self.top = max(self.top, reg)
        if isinstance(v, dict):
            self.code.append(lp.abx(OP["NEWTABLE"], reg, len(v)))
            for name, item in v.items():
                self.value(reg + 1, item)
                self.code.append(lp.abc(OP["SETTABLE"], reg + 1, reg, 250 + self.const(name)))
        elif isinstance(v, list):
            self.code.append(lp.abx(OP["NEWTABLE"], reg, len(v)))
            for i, item in enumerate(v):
                self.value(reg + 1 + i, item)
            self.code.append(lp.abx(OP["SETLIST"], reg, len(v) - 1))
        elif isinstance(v, tuple):  # ("global", name): a global's value
            self.code.append(lp.abx(OP["GETGLOBAL"], reg, self.const(v[1])))
        elif isinstance(v, int):
            self.code.append(lp.abx(OP["LOADINT"], reg, v + lp.SBX_BIAS))
        else:
            self.code.append(lp.abx(OP["LOADK"], reg, self.const(v)))

    def chunk(self, table, name):
        self.const(table["name"])
        self.value(0, table)
        self.code += [lp.abx(OP["SETGLOBAL"], 0, self.const(name)), lp.abc(OP["RETURN"], 0, 0, 0)]
        body = string("=(none)") + struct.pack("<5i", 0, 0, 0, 0, self.top + 1) + struct.pack("<ii", 0, 0)
        body += struct.pack("<i", len(self.k))
        for tag, v in self.k:
            body += bytes([tag]) + (struct.pack("<i", len(v)) + v if tag == lp.STRING else struct.pack("<f", v))
        return HEADER + body + struct.pack("<ii", 0, len(self.code)) + struct.pack(f"<{len(self.code)}I", *self.code)


def string(s):
    return struct.pack("<i", len(s) + 1) + s.encode() + b"\0"


def script(table=None, name="Blaster"):
    return Compiler().chunk(table or WEAPON, name)


def run(chunk):
    """the globals after running the main function (an interpreter of the table-building instructions);
    lists come out as lists, unknown globals as ("global", name)"""
    f = lp.read(chunk)
    regs, globs = [None] * f.header[4], {}

    def k(i):
        return lp.constant(f, i)

    for w in f.code:
        o, a = lp.op(w), lp.a_of(w)
        if o == OP["NEWTABLE"]:
            regs[a] = {}
        elif o == OP["LOADK"]:
            regs[a] = k(lp.bx_of(w))
        elif o == OP["LOADINT"]:
            regs[a] = lp.bx_of(w) - lp.SBX_BIAS
        elif o == OP["LOADNIL"]:
            for r in range(a, lp.b_of(w) + 1):
                regs[r] = None
        elif o == OP["GETGLOBAL"]:
            regs[a] = globs.get(k(lp.bx_of(w)), ("global", k(lp.bx_of(w))))
        elif o == OP["SETTABLE"]:
            if regs[a] is not None:
                regs[lp.b_of(w)][k(lp.c_of(w) - 250)] = regs[a]
        elif o == OP["SETLIST"]:
            n = lp.bx_of(w)
            for i in range(1, n % 32 + 2):
                regs[a][n - n % 32 + i] = regs[a + i]
        elif o == OP["SETGLOBAL"]:
            globs[k(lp.bx_of(w))] = regs[a]
        elif o == OP["RETURN"]:
            break
        else:
            raise AssertionError(f"op {o} in a synthetic script")

    def plain(v):
        if isinstance(v, dict):
            if v and all(isinstance(i, int) for i in v):
                return [plain(v[i]) for i in sorted(v)]
            return {key: plain(x) for key, x in v.items()}
        return v

    return {name: plain(v) for name, v in globs.items()}


def close(a, b):
    """equal, floats to float32 precision"""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(map(close, a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) < 1e-6
    return a == b


def test_the_interpreter_and_the_reader_agree_with_the_source():
    chunk = script()
    assert close(run(chunk)["Blaster"], WEAPON)
    assert lp.write(lp.read(chunk)) == chunk
    flat = dict(lp.flatten(lp.weapon_table(lp.read(chunk)), compact=True))
    assert lp.show(flat["FireParams[1].BulletTrail.colorA"]) == "{1, 1, 1}"
    assert lp.show(flat["FireParams[1].fire_rate"]) == "0.2"
    assert lp.show(flat["FireParams[2].MuzzleParticle.effect"]) == "'GFX_Flash2'"
    assert lp.show(flat["eGroup"]) == "<EWeaponGroup_Secondary>"


def test_patch_sets_values_lists_nil_and_wildcards():
    new, report = lp.patch(
        script(),
        {
            "FireParams[*].MuzzleParticle.effect": "GFX_Smoke",
            "FireParams[1].MuzzleParticle.bulletCases": None,
            "FireParams[1].BulletTrail.colorA": [0.2, 0.6, 1],
            "FireParams[1].BulletTrail.speed": 40,
            "FireParams[1].BulletTrail.width": 0.08,
            "FireParams[1].fire_rate": 0.05,  # the second fire mode keeps its own
            "eGroup": 3,
        },
    )
    want = json.loads(json.dumps(WEAPON))
    want["eGroup"] = 3
    fp = want["FireParams"]
    fp[0]["MuzzleParticle"] = {"effect": "GFX_Smoke"}
    fp[1]["MuzzleParticle"]["effect"] = "GFX_Smoke"
    fp[0]["BulletTrail"].update(colorA=[0.2, 0.6, 1], speed=40, width=0.08)
    fp[0]["fire_rate"] = 0.05
    assert close(run(new)["Blaster"], want)
    assert ("FireParams[1].BulletTrail.colorA[2]", "1", "0.6") in report
    assert not [r for r in report if r[0] == "FireParams[1].BulletTrail.colorA[3]"]  # 1 already: no change
    assert ("FireParams[1].MuzzleParticle.bulletCases", "'GFX_Cases'", "nil") in report
    assert ("eGroup", "<EWeaponGroup_Secondary>", "3") in report
    assert lp.check(script(), new, report)  # nothing else changed
    # the same chunk size but for new constants: instructions are changed in place
    assert len(lp.read(new).code) == len(lp.read(script()).code)


def test_patch_reuses_constants_and_loads_integers_inline():
    f = lp.read(script())
    count = len(f.k)
    new, _ = lp.patch(script(), {"FireParams[2].damage": 0.2, "FireParams[1].damage": 100000})
    g = lp.read(new)
    assert len(g.k) == count  # 0.2 is there already, 100000 is a LOADINT
    assert run(new)["Blaster"]["FireParams"][0]["damage"] == 100000


def test_patch_adds_missing_fields_and_tables():
    light = {"color": [0.3, 0.6, 1.0], "diffuseMul": 1, "radius": 2.5}
    new, report = lp.patch(
        script(),
        {
            "FireParams[*].MuzzleLight": light,
            "FireParams[2].BulletTrail": {"colorA": [1, 0.4, 0.9], "speed": 30, "texture": "tracer.xbt"},
            "FireParams[1].BulletTrail.alphaMul": 0.7,
            "FireParams[1].MuzzleParticle.effect": "GFX_Smoke",
        },
    )
    got = run(new)["Blaster"]["FireParams"]
    assert close(got[0]["MuzzleLight"], light) and close(got[1]["MuzzleLight"], light)
    assert close(got[1]["BulletTrail"], {"colorA": [1, 0.4, 0.9], "speed": 30, "texture": "tracer.xbt"})
    assert close(got[0]["BulletTrail"]["alphaMul"], 0.7)
    assert got[0]["MuzzleParticle"]["effect"] == "GFX_Smoke" and got[0]["damage"] == 8
    assert ("FireParams[2].MuzzleLight", "(not set)", "{color = {0.3, 0.6, 1}, diffuseMul = 1, radius = 2.5}") in report
    rows = lp.check(script(), new, report)
    assert ("FireParams[1].MuzzleLight.color[3]", "(not set)", "1") in rows
    # the new code needs more registers: the stack size grows with it
    assert lp.read(new).header[4] > lp.read(script()).header[4]
    # and a dump of the result shows the new tables like the script's own
    flat = dict(lp.flatten(lp.weapon_table(lp.read(new)), compact=True))
    assert lp.show(flat["FireParams[2].MuzzleLight.color"]) == "{0.3, 0.6, 1}"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"FireParams[1].Nothing.at_all": 1}, "names nothing"),
        ({"FireParams[1].BulletTrail.colorA": [1, 1]}, "has 3 items"),
        ({"FireParams[1].BulletTrail": 1}, "is a table"),
        ({"FireParams[1].damage": [1, 2]}, "is a value"),
        ({"FireParams[1].damage": True}, "no true and false"),
        ({"FireParams[1].BulletTrail.colorA[4]": 1}, "list item"),
        ({"FireParams[1]..damage": 1}, "not a path"),
    ],
)
def test_patch_refuses_what_it_cannot_do(changes, message):
    with pytest.raises(ValueError, match=message):
        lp.patch(script(), changes)


def test_check_notices_a_change_nobody_asked_for():
    new, report = lp.patch(script(), {"FireParams[1].damage": 9})
    f = lp.read(new)
    i = next(i for i, (tag, v) in enumerate(f.k) if v == b"GFX_Flash\0")
    f.k[i] = (lp.STRING, b"GFX_Other\0")
    with pytest.raises(ValueError, match="changed although"):
        lp.check(script(), lp.write(f), report)


def game(tmp_path, chunks, orig=None):
    """a game folder whose lua.dat holds the chunks under their weapon paths, and lua.dat.orig if given"""
    folder = tmp_path / "game"
    folder.mkdir()
    dat, entries = b"", []
    for name, chunk in chunks.items():
        entries.append((len(dat), len(chunk), zlib.crc32(("\\" + lp.script_path(name)).lower().encode()) & 0xFFFFFFFF))
        dat += chunk
    entries.sort(key=lambda e: e[2])
    (folder / "lua.dat").write_bytes(dat)
    (folder / "lua.fat").write_bytes(
        b"DAT2" + struct.pack("<I", len(entries)) + b"".join(struct.pack("<III", *e) for e in entries)
    )
    if orig is not None:
        (folder / "lua.dat.orig").write_bytes(orig)
    return folder


def test_run_config_writes_each_script_where_the_mod_menu_finds_it(tmp_path, capsys):
    other = dict(WEAPON, name="Other")
    folder = game(tmp_path, {"Blaster": script(), "Other": script(other, "Other")})
    config = tmp_path / "mod.json"
    config.write_text(
        json.dumps(
            {
                "lua": {
                    "game": "game",
                    "out": "mod/lua",
                    "set": {"FireParams[*].MuzzleParticle.effect": "GFX_Smoke"},
                    "scripts": {"Blaster": {"FireParams[1].damage": 20}, "Other": {}},
                }
            }
        )
    )
    done = lp.run_config(config)
    written = tmp_path / "mod" / "lua" / "scripts" / "default" / "entities" / "weapons" / "blaster.lua_compiled"
    assert run(written.read_bytes())["Blaster"]["FireParams"][0]["damage"] == 20
    assert run((written.parent / "other.lua_compiled").read_bytes())["Other"]["FireParams"][1]["MuzzleParticle"] == {
        "effect": "GFX_Smoke"
    }
    assert ("Blaster", "FireParams[1].damage", "8", "20") in done
    # diff reads the mod's files back against the game's scripts on its own
    files = lp.mod_files(tmp_path / "mod" / "lua")
    assert [rel for rel, _ in files] == [lp.script_path("Blaster"), lp.script_path("Other")]
    assert lp.diff(script(), files[0][1].read_bytes()) == [
        ("FireParams[1].damage", "8", "20"),
        ("FireParams[1].MuzzleParticle.effect", "'GFX_Flash'", "'GFX_Smoke'"),
        ("FireParams[2].MuzzleParticle.effect", "'GFX_Flash2'", "'GFX_Smoke'"),
    ]
    assert (folder / "lua.dat").read_bytes().startswith(script())  # the game's files stay as they are
    assert "not the disc's" not in capsys.readouterr().out


def test_run_config_dry_run_writes_nothing_and_notes_a_changed_lua_dat(tmp_path, capsys):
    game(tmp_path, {"Blaster": script()}, orig=script(dict(WEAPON, FPModel="other.xbg")))
    config = tmp_path / "mod.json"
    config.write_text(json.dumps({"game": "game", "out": "mod", "scripts": {"Blaster": {"FireParams[1].damage": 1}}}))
    assert lp.run_config(config, dry_run=True) == [("Blaster", "FireParams[1].damage", "8", "1")]
    assert not (tmp_path / "mod").exists()
    assert "not the disc's" in capsys.readouterr().out


def test_unknown_scripts_and_chunks_are_refused(tmp_path):
    folder = game(tmp_path, {"Blaster": script()})
    with pytest.raises(SystemExit, match="has no"):
        lp.find(folder, "Missing")
    with pytest.raises(ValueError):
        lp.read(script()[:-3])
    assert lp.script_path("Blaster") == "scripts\\default\\entities\\weapons\\blaster.lua_compiled"
    assert lp.script_path("/Scripts/Default/GameRules.lua") == "Scripts\\Default\\GameRules.lua_compiled"
