"""Change values in the games' compiled weapon scripts (lua.dat, re/notes/WEAPONS.md) and write each changed
script as a mod's file (README.md, Mods), so that switching the mod off brings the game's own back.

  python -B tools/lua_patch.py list --game <folder>                 the weapon scripts and their paths
  python -B tools/lua_patch.py dump <script> --game <folder> [--grep <text>]    the values a script sets
  python -B tools/lua_patch.py patch <config.json> [--dry-run]      write the scripts a config changes
  python -B tools/lua_patch.py diff <file or folder> --game <folder>   what a mod's scripts change, old -> new

  --game   a game's game folder (the one with lua.dat and lua.fat)
  <script> a weapon (Berretta, P90: the script that builds that table) or a script's path in lua.dat

lua.dat stores no names: a file is the CRC-32 of its path plus ".lua_compiled", as in
scripts\\default\\entities\\weapons\\p90.lua_compiled; a mod holds it as lua\\scripts\\...\\p90.lua_compiled.

The config (paths relative to it): the "lua" part of a weapon mod's config, or the whole file.

  "lua": {
    "game": "../FarCryInstincts/game",
    "out": "../../mods/instincts/halo-needler/lua",
    "set": {"FireParams[*].MuzzleLight.color": [1.0, 0.35, 0.85],      for every script below
            "FireParams[*].MuzzleParticle.bulletCases": null},
    "scripts": {"P90": {"FireParams[1].BulletTrail.speed": 30}}        each script, with its own on top
  }

A path goes from the weapon's table: field names, [n] for a list's n-th item (from 1), * or [*] for any
field or item. A value is a number, a string, null (the field is not set: gone), a list (the items of a
table that has as many) or an object (fields of a table). A field the script does not set is added to its
table where the table is built, a new table from an object or a list. Lua 4.1 has no true and false: the
scripts use 1 and 0.

The scripts come from the game's lua.dat as it is, so other changes made to it (tools/weapon_range.py) are
in the mod's copy too; patch says so when a script differs from lua.dat.orig. It reads every written file
back and prints each value old -> new.
"""

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import luadat  # noqa: E402

# Lua 4.1 (work) opcodes, as the games' scripts use them
OPS = (
    "MOVE LOADK LOADINT LOADNIL LOADUPVAL GETGLOBAL GETTABLE SETGLOBAL SETTABLE NEWTABLE SELF ADD SUB MUL DIV "
    "POW UNM NOT CONCAT JMP CJMP TESTEQ TESTNE TESTLT TESTLE TESTGT TESTGE TESTT TESTF NILJMP CALL RETURN "
    "FORPREP FORLOOP TFORPREP TFORLOOP SETLIST SETLIST0 CLOSURE"
).split()
OP = {name: i for i, name in enumerate(OPS)}
JUMPS = {OP[n] for n in ("JMP", "CJMP", "FORPREP", "FORLOOP", "TFORPREP", "TFORLOOP")}
SBX_BIAS = 0x1FFFF
RK_CONSTANT = 250  # an RK operand (10 bits) from here up names constant RK - 250
RK_TOP = 0x3FF
FLUSH = 32  # SETLIST: R(A)[Bx - Bx % FLUSH + i] = R(A + i), 1 <= i <= Bx % FLUSH + 1
NUMBER, STRING, NIL = 2, 3, 0  # constant tags
WEAPONS = "scripts\\default\\entities\\weapons\\"
SUFFIX = ".lua_compiled"


# --- instructions -------------------------------------------------------------------------------------
# op = w & 0x3F, C = (w >> 6) & 0x3FF, B = (w >> 16) & 0xFF, A = w >> 24; Bx = (w >> 6) & 0x3FFFF


def op(w):
    return w & 0x3F


def a_of(w):
    return w >> 24


def b_of(w):
    return (w >> 16) & 0xFF


def c_of(w):
    return (w >> 6) & 0x3FF


def bx_of(w):
    return (w >> 6) & 0x3FFFF


def abc(o, a, b, c):
    return (a << 24) | (b << 16) | (c << 6) | o


def abx(o, a, bx):
    return (a << 24) | (bx << 6) | o


# --- chunks: read and written back byte for byte ---------------------------------------------------


class Function:
    """source, five header ints (the last the stack size), line info, locals, constants as (tag, value),
    nested functions, code"""


def read(chunk):
    """a script's main Function; ValueError when it is not one this reader understands"""
    if chunk[:4] != b"\x1bLua":
        raise ValueError("not a Lua chunk")
    p = 18

    def i32():
        nonlocal p
        v = struct.unpack_from("<i", chunk, p)[0]
        p += 4
        return v

    def string():
        nonlocal p
        n = i32()
        s = bytes(chunk[p : p + n]) if n else None
        p += n
        return s

    def function():
        nonlocal p
        f = Function()
        f.source = string()
        f.header = [i32() for _ in range(5)]
        f.lines = [i32() for _ in range(i32())]
        f.locals = [(string(), i32(), i32()) for _ in range(i32())]
        f.k = []
        for _ in range(i32()):
            tag = chunk[p]
            p += 1
            if tag == STRING:
                f.k.append((tag, string()))
            elif tag == NIL:
                f.k.append((tag, None))
            else:
                f.k.append((tag, struct.unpack_from("<f", chunk, p)[0]))
                p += 4
        f.protos = [function() for _ in range(i32())]
        n = i32()
        f.code = list(struct.unpack_from(f"<{n}I", chunk, p))
        p += 4 * n
        return f

    try:
        f = function()
    except (struct.error, IndexError):
        raise ValueError("a Lua chunk this reader does not understand")
    if p != len(chunk):
        raise ValueError("a Lua chunk this reader does not understand")
    f.chunk_header = bytes(chunk[:18])
    return f


def write(main):
    out = bytearray(main.chunk_header)

    def string(s):
        out.extend(struct.pack("<i", len(s) if s is not None else 0))
        out.extend(s or b"")

    def function(f):
        string(f.source)
        out.extend(struct.pack("<5i", *f.header))
        out.extend(struct.pack(f"<i{len(f.lines)}i", len(f.lines), *f.lines))
        out.extend(struct.pack("<i", len(f.locals)))
        for name, start, end in f.locals:
            string(name)
            out.extend(struct.pack("<ii", start, end))
        out.extend(struct.pack("<i", len(f.k)))
        for tag, v in f.k:
            out.append(tag)
            if tag == STRING:
                string(v)
            elif tag != NIL:
                out.extend(struct.pack("<f", v))
        out.extend(struct.pack("<i", len(f.protos)))
        for g in f.protos:
            function(g)
        out.extend(struct.pack(f"<i{len(f.code)}I", len(f.code), *f.code))

    function(main)
    return bytes(out)


def text(s):
    return s[:-1].decode("latin-1") if s else ""


def constant(f, i):
    tag, v = f.k[i]
    return text(v) if tag == STRING else v


# --- what the main function builds ------------------------------------------------------------------


class Table:
    """a table the code builds (NEWTABLE at pc into register reg): its fields and list items as the values
    or tables stored there"""

    def __init__(self, pc, reg):
        self.pc, self.reg = pc, reg
        self.fields, self.items = {}, {}


class Value:
    """a value an instruction (pc) puts into one register: a constant, a global, or something computed"""

    def __init__(self, pc, value, known=True):
        self.pc, self.value, self.known = pc, value, known
        self.stores = 0


def tables(f):
    """{global name: Table} for the tables the main function builds and stores in globals"""
    regs, globs = {}, {}

    def key(c):
        return constant(f, c - RK_CONSTANT) if c >= RK_CONSTANT else None

    def store(t, k, v):
        if isinstance(t, Table) and k is not None and v is not None:
            (t.items if isinstance(k, int) else t.fields)[k] = v
            if isinstance(v, Value):
                v.stores += 1

    for pc, w in enumerate(f.code):
        o, a = op(w), a_of(w)
        if o == OP["NEWTABLE"]:
            regs[a] = Table(pc, a)
        elif o == OP["LOADK"]:
            regs[a] = Value(pc, constant(f, bx_of(w)))
        elif o == OP["LOADINT"]:
            regs[a] = Value(pc, bx_of(w) - SBX_BIAS)
        elif o == OP["LOADNIL"]:
            for r in range(a, b_of(w) + 1):
                regs[r] = Value(pc, None, known=a == b_of(w))
        elif o == OP["GETGLOBAL"]:
            name = constant(f, bx_of(w))
            regs[a] = globs[name] if isinstance(globs.get(name), Table) else Value(pc, name, known=False)
        elif o == OP["SETGLOBAL"]:
            globs[constant(f, bx_of(w))] = regs.get(a)
        elif o == OP["MOVE"]:
            src = regs.get(b_of(w))
            regs[a] = src if isinstance(src, Table) else Value(pc, getattr(src, "value", None), known=False)
        elif o == OP["GETTABLE"]:
            t, k = regs.get(b_of(w)), key(c_of(w))
            got = t.fields.get(k) if isinstance(t, Table) else None
            name = f"{getattr(regs.get(b_of(w)), 'value', '?')}.{k}"
            regs[a] = got if isinstance(got, Table) else Value(pc, name, known=False)
        elif o == OP["SETTABLE"]:
            store(regs.get(b_of(w)), key(c_of(w)), regs.get(a))
        elif o == OP["SETLIST"]:
            bx = bx_of(w)
            for i in range(1, bx % FLUSH + 2):
                store(regs.get(a), bx - bx % FLUSH + i, regs.get(a + i))
        elif o == OP["CALL"]:
            for r in [r for r in regs if r >= a]:
                del regs[r]
        elif o not in JUMPS and o not in (OP["RETURN"], OP["SETLIST0"]):
            regs.pop(a, None)
    return {name: t for name, t in globs.items() if isinstance(t, Table)}


def weapon_table(f):
    """the table the script is about: the global named by its first string, else the first one it builds"""
    found = tables(f)
    if not found:
        raise ValueError("the script builds no global table")
    first = next((constant(f, i) for i, (tag, _) in enumerate(f.k) if tag == STRING), None)
    return found.get(first, next(iter(found.values())))


def show(v):
    if isinstance(v, Value):
        if not v.known:
            return f"<{v.value}>"
        return repr(v.value) if isinstance(v.value, str) else "nil" if v.value is None else f"{v.value:g}"
    if isinstance(v, Table) and not v.fields and v.items and all(isinstance(i, Value) for i in v.items.values()):
        return "{" + ", ".join(show(v.items[i]) for i in sorted(v.items)) + "}"
    return "{...}"


def join(prefix, kind, k):
    return f"{prefix}[{k}]" if kind == "item" else f"{prefix}.{k}" if prefix else k


def flatten(t, prefix="", compact=False):
    """(path, value or table) for everything under t, depth first; compact: a list of values as one entry"""
    out = []
    for kind, pool in (("field", t.fields), ("item", dict(sorted(t.items.items())))):
        for k, v in pool.items():
            path = join(prefix, kind, k)
            out.append((path, v))
            if isinstance(v, Table) and not (compact and show(v) != "{...}"):
                out.extend(flatten(v, path, compact))
    return out


# --- paths ------------------------------------------------------------------------------------------

STEP = re.compile(r"\.?([A-Za-z_][A-Za-z0-9_]*|\*)|\[(\d+|\*)\]")


def steps(path):
    """("field", name or "*") / ("item", n or "*") for each step of a path"""
    out, at = [], 0
    while at < len(path):
        m = STEP.match(path, at)
        if not m or (at == 0 and path.startswith(".")) or m.end() == at:
            raise ValueError(f"not a path: {path!r}")
        field, item = m.groups()
        out.append(("field", field) if field else ("item", "*" if item == "*" else int(item)))
        at = m.end()
    return out


def children(t, step):
    kind, k = step
    pool = t.fields if kind == "field" else t.items
    return list(pool) if k == "*" else [k]


# --- patching ---------------------------------------------------------------------------------------


class Patch:
    def __init__(self, f):
        self.f = f
        self.edits = {}  # pc: new instruction
        self.inserts = {}  # pc: instructions after it
        self.report = []  # (path, old, new)

    def k(self, value):
        """the constant index of value (a string or a number), added when the function lacks it"""
        if isinstance(value, str):
            tag, raw = STRING, value.encode("latin-1") + b"\0"
        else:
            tag, raw = NUMBER, struct.unpack("<f", struct.pack("<f", value))[0]
        for i, (t, v) in enumerate(self.f.k):
            if t == tag and v == raw:
                return i
        self.f.k.append((tag, raw))
        return len(self.f.k) - 1

    def key(self, name):
        i = self.k(name)
        if RK_CONSTANT + i > RK_TOP:
            raise ValueError(f"too many constants for the field name {name!r}")
        return RK_CONSTANT + i

    def load(self, reg, value):
        """the instruction that puts a number, a string or nil into reg"""
        if value is None:
            return abc(OP["LOADNIL"], reg, reg, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"not a value for a script: {value!r} (Lua 4.1 has no true and false: 1 and 0)")
        if not isinstance(value, str) and float(value).is_integer() and -SBX_BIAS <= value <= 0x3FFFF - SBX_BIAS:
            return abx(OP["LOADINT"], reg, int(value) + SBX_BIAS)
        return abx(OP["LOADK"], reg, self.k(value))

    def build(self, reg, value):
        """code that leaves value (a scalar, a list or an object) in reg, using the registers above it; the
        code and the highest register used"""
        if isinstance(value, list):
            if not 0 < len(value) <= FLUSH:
                raise ValueError(f"a list of 1 to {FLUSH} items, not {len(value)}")
            code, top = [abx(OP["NEWTABLE"], reg, len(value))], reg
            for i, item in enumerate(value):
                more, t = self.build(reg + 1 + i, item)
                code += more
                top = max(top, t)
            return code + [abx(OP["SETLIST"], reg, len(value) - 1)], top
        if isinstance(value, dict):
            code, top = [abx(OP["NEWTABLE"], reg, len(value))], reg
            for name, item in value.items():
                more, t = self.build(reg + 1, item)
                code += more + [abc(OP["SETTABLE"], reg + 1, reg, self.key(name))]
                top = max(top, t)
            return code, top
        return [self.load(reg, value)], reg

    def put(self, t, step, k, value, path):
        pool = t.fields if step == "field" else t.items
        have = pool.get(k)
        if isinstance(have, Table):
            if isinstance(value, list):
                if len(value) != len(have.items):
                    raise ValueError(f"{path} has {len(have.items)} items, not {len(value)}")
                for i, item in enumerate(value):
                    self.put(have, "item", i + 1, item, f"{path}[{i + 1}]")
            elif isinstance(value, dict):
                for name, item in value.items():
                    self.put(have, "field", name, item, f"{path}.{name}")
            else:
                raise ValueError(f"{path} is a table, not a value")
        elif isinstance(have, Value):
            if isinstance(value, (list, dict)):
                raise ValueError(f"{path} is a value, not a table")
            if not have.known and op(self.f.code[have.pc]) == OP["LOADNIL"]:
                raise ValueError(f"{path} is set by a LOADNIL of several registers")
            if have.known and show(have) == shown(value):
                return  # as asked already
            if have.stores != 1:
                raise ValueError(f"{path}: its value is used elsewhere too")
            self.edits[have.pc] = self.load(a_of(self.f.code[have.pc]), value)
            self.report.append((path, show(have), shown(value)))
        elif value is not None:
            if step == "item":
                raise ValueError(f"{path}: a list item the script does not set")
            code, top = self.build(t.reg + 1, value)
            code.append(abc(OP["SETTABLE"], t.reg + 1, t.reg, self.key(k)))
            self.inserts.setdefault(t.pc, []).extend(code)
            self.f.header[4] = max(self.f.header[4], top + 1)
            self.report.append((path, "(not set)", shown(value)))

    def apply(self, root, changes):
        for path, value in changes.items():
            route = steps(path)
            parents = [("", root)]
            for kind, k in route[:-1]:
                parents = [
                    (join(prefix, kind, key), c)
                    for prefix, t in parents
                    for key in children(t, (kind, k))
                    if isinstance(c := (t.fields if kind == "field" else t.items).get(key), Table)
                ]
            done = 0
            for prefix, t in parents:
                for k in children(t, route[-1]):
                    self.put(t, route[-1][0], k, value, join(prefix, route[-1][0], k))
                    done += 1
            if not done:
                raise ValueError(f"{path} names nothing in the script")
        if self.inserts and any(op(w) in JUMPS for w in self.f.code):
            raise ValueError("fields can only be added to a script without jumps in its main function")
        if self.inserts and self.f.lines:
            raise ValueError("fields can only be added to a script without line info")
        code = []
        for pc, w in enumerate(self.f.code):
            code.append(self.edits.get(pc, w))
            code.extend(self.inserts.get(pc, ()))
        self.f.code = code


def shown(value):
    if isinstance(value, list):
        return "{" + ", ".join(shown(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {shown(v)}" for k, v in value.items()) + "}"
    if value is None:
        return "nil"
    return repr(value) if isinstance(value, str) else f"{value:g}"


def patch(chunk, changes):
    """(the changed chunk, [(path, old, new)]) for {path: value}"""
    main = read(chunk)
    p = Patch(main)
    p.apply(weapon_table(main), changes)
    return write(main), p.report


# --- lua.dat ------------------------------------------------------------------------------------------


def script_path(script):
    """the path in lua.dat of a weapon's script, or of a path given as one"""
    if "\\" in script or "/" in script:
        path = script.replace("/", "\\").lstrip("\\")
        if path.lower().endswith(SUFFIX):
            return path
        return path + "_compiled" if path.lower().endswith(".lua") else path + SUFFIX
    return WEAPONS + script.lower() + SUFFIX


def name_hash(path):
    return zlib.crc32(("\\" + path.lower()).encode("latin-1")) & 0xFFFFFFFF


def scripts(game, dat="lua.dat"):
    """{name hash: chunk} of a game folder's lua.dat (or lua.dat.orig)"""
    data = (Path(game) / dat).read_bytes()
    return {h: data[o : o + s] for o, s, h in luadat.index((Path(game) / "lua.fat").read_bytes())}


def find(game, script):
    path = script_path(script)
    chunk = scripts(game).get(name_hash(path))
    if chunk is None:
        raise SystemExit(f"error: {game}/lua.dat has no {path}")
    return path, chunk


def changed_from_original(game, path):
    orig = Path(game) / "lua.dat.orig"
    return orig.is_file() and scripts(game, "lua.dat.orig").get(name_hash(path)) != find(game, path)[1]


def resolve(t, path):
    """the values and tables a path names under t: [(path, value or table)]"""
    found = [("", t)]
    for kind, k in steps(path):
        found = [
            (join(prefix, kind, key), c)
            for prefix, t in found
            if isinstance(t, Table)
            for key in children(t, (kind, k))
            if (c := (t.fields if kind == "field" else t.items).get(key)) is not None
        ]
    return found


def run_config(path, dry_run=False):
    """write the scripts a config changes; [(script, path, old, new)] as the written files have them"""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg = cfg.get("lua", cfg)
    base = Path(path).resolve().parent
    game, out = (base / cfg["game"]).resolve(), (base / cfg["out"]).resolve()
    done = []
    for script, own in cfg["scripts"].items():
        rel, chunk = find(game, script)
        new, report = patch(chunk, {**cfg.get("set", {}), **own})
        target = out / Path(*rel.lower().split("\\"))
        note = " (lua.dat has other changes in it: not the disc's)" if changed_from_original(game, rel) else ""
        print(f"{script}: {rel}{note}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(new)
            new = target.read_bytes()
        for p, old, now in check(chunk, new, report):
            print(f"  {p}: {old} -> {now}")
            done.append((script, p, old, now))
        print("  (dry run: nothing written)" if dry_run else f"  -> {target}")
    return done


def check(chunk, new, report):
    """[(path, old, new)] read back from the changed chunk for each change, a new table's values one by one;
    ValueError when anything else differs from the original"""
    before, after = weapon_table(read(chunk)), weapon_table(read(new))
    was, now = dict(flatten(before)), dict(flatten(after))
    out = []
    for p, old, _ in report:
        got = now.get(p)
        if isinstance(got, Table):
            out += [(q, "(not set)", show(v)) for q, v in flatten(got, p) if isinstance(v, Value)]
        else:
            out.append((p, old, show(got) if got is not None else "nil"))
    changed = {p for p, _, _ in report}
    for p, v in was.items():
        if isinstance(v, Value) and p not in changed and (p not in now or show(now[p]) != show(v)):
            raise ValueError(f"{p} changed although the config does not name it")
    for p in now:
        if p not in was and not any(p == c or p.startswith(c + ".") or p.startswith(c + "[") for c in changed):
            raise ValueError(f"{p} appeared although the config does not name it")
    return out


def diff(chunk, new):
    """[(path, old, new)] for every value that differs between two versions of a script"""
    was, now = dict(flatten(weapon_table(read(chunk)))), dict(flatten(weapon_table(read(new))))
    out = []
    for p in [*was, *(q for q in now if q not in was)]:
        old = show(was[p]) if isinstance(was.get(p), Value) else "(not set)" if p not in was else None
        got = show(now[p]) if isinstance(now.get(p), Value) else "(not set)" if p not in now else None
        if old != got and not (old is None or got is None):
            out.append((p, old, got))
    return out


def mod_files(where):
    """(path in lua.dat, file) for a mod's script file or every one under a folder"""
    files = [Path(where)] if Path(where).is_file() else sorted(Path(where).rglob("*" + SUFFIX))
    out = []
    for f in files:
        parts = [q.lower() for q in f.resolve().parts]
        if "scripts" not in parts:
            raise ValueError(f"{f} is not under a scripts folder")
        out.append(("\\".join(f.resolve().parts[parts.index("scripts") :]), f))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("list", "dump", "patch", "diff"))
    ap.add_argument("what", nargs="?", help="dump: the script; patch: the config; diff: a mod's file or folder")
    ap.add_argument("--game")
    ap.add_argument("--grep")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        if a.command == "patch":
            run_config(a.what, a.dry_run)
            return
        if not a.game:
            raise SystemExit("error: --game names the game folder (with lua.dat)")
        if a.command == "diff":
            for rel, f in mod_files(a.what):
                _, chunk = find(a.game, rel)
                print(rel)
                for p, old, new in diff(chunk, f.read_bytes()):
                    print(f"  {p}: {old} -> {new}")
        elif a.command == "list":
            for h, chunk in sorted(scripts(a.game).items()):
                if not chunk.startswith(b"\x1bLua"):
                    continue
                name = luadat.name(luadat.parse(chunk))
                if name and name_hash(script_path(name)) == h:
                    print(f"{name:24s} {script_path(name)}")
        else:
            _, chunk = find(a.game, a.what)
            for p, v in flatten(weapon_table(read(chunk)), compact=True):
                if a.grep is None or a.grep.lower() in p.lower():
                    print(f"{p} = {show(v)}")
    except ValueError as e:
        raise SystemExit(f"error: {e}")
    except PermissionError as e:
        raise SystemExit(f"error: {e.filename} cannot be written")


if __name__ == "__main__":
    main()
