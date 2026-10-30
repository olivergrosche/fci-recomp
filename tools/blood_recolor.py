"""The games' blood (re/notes/BLOOD.md) as mod folders for the game's mod menu (README.md, Mods): the
hard-coded bullet-hit blood's textures recoloured, its sprays scaled, the stain a hit leaves on the hit
character made larger with the game's splat texture, and particle tints recoloured where an effect takes its
blood colour from its tint.

  python -B tools/blood_recolor.py <config.json> [mod ...] [--check <folder>] [--dry-run]

  mod        build only these mods of the config (default all)
  --check    write before/after swatches of every recoloured texture and tint (PNG) to the folder
  --dry-run  say what would be written, write nothing

The config (paths relative to it; every key but "colour" can be given for all mods at the top and per mod,
null switching a part off):

  {
    "game": "../../FarCryInstincts/game",                  read only: the files come from its archives
    "archives": ["levels/[0-9]*"],                          the level archives to write for (default all)
    "out": "../../mods/instincts",                          the mods folder: <out>/<mod>/<archive>/<path>
    "group": "Halo: effects", "credit": "...",              mod.ini defaults
    "colours": {"elite": {"from": [142, 25, 16], "to": [90, 80, 240]}, ...},
    "textures": ["magma/textures/hud/damage_21.xbt", ...],   recoloured where an archive holds them
    "spray": {"libraries": ["GFX_Particle_Bullet_Hit_Blood_Big", ...], "texture": "damage_21",
              "size": 2.5, "count": 2, "speed": 1.3, "life": 1.4},
    "stains": {"materials": [3, 30, 31, 32, 33, 34], "size": 0.4, "variance": 0.1,
               "texture": "textures_xbox/decal/gfx_decal_bullet_hit_flesh_a.xbt",
               "splat": {"game": "D:/.../FarCryInstincts/game", "archive": "levels/10_Dead_Marshes/10_Dead_Marshes",
                         "path": "textures_xbox/decal/gfx_decal_explosion_bloodsplat_df.xbt"}},
    "tints": {"GFX_Explosions_Sapper": "flood"},            a library's reddish tints in that colour
    "mods": {
      "halo-blood-elite": {"colour": "elite", "name": "...", "description": "..."},
      "halo-blood-red": {"colour": null},                    the game's red: sprays and stains only
      "halo-blood-sapper": {"set": "sapper", "colour": "flood", "archives": ["levels/1[013]_*"],
                            "textures": [...], "spray": null, "stains": null, "tints": null},
      "halo-blood-mixed": {"colour": "elite", "levels": {"levels/10_*": "flood"}}   other colours per archive
    }
  }

A colour is a linear map that takes "from" (the blood's red) to "to" and leaves greys grey: with m the mean
of green and blue, out = m + (r - m) * T, T = (to - m_from) / (r_from - m_from) per channel. It is linear in
r, g, b, so it is applied to the two colour endpoints of each DXT block (each mip level by itself): the
texture keeps its shapes, its alpha and its block indices, only the palette of each block moves. An
endpoint pair whose order the map turns round is swapped back with its indices, so a decoder that reads
the order (DXT1's three-colour blocks) sees the block as before. A mod without a colour writes no recoloured
textures.

The particle library (levels/<level>/<level>_DepLoadParticles.xml) gets one pass: in the "spray" libraries
every active emitter that draws "texture" has Size and SizeSpeed times "size", Count times "count" (at least
1), Speed times "speed", LifeTime times "life"; in the "tints" libraries reddish StartColor and EndColor (red
at least 0.1, green and blue at most a third of it) go through that library's colour. The rest of the file
stays byte for byte. "stains" sets the size (+0x10) and its random spread (+0x60) of the hit decal of the
given materials in particles/materials.dat (all of them must use the flesh decal, 6) and puts the "splat"
texture, recoloured, in place of the hit decal's texture.

Mods of one "set" (default "blood") are alternatives and may write the same files (the menu keeps one of them
on); mods of different sets must not, and the tool refuses a config where they do. Each mod folder lists what
it wrote in .files; a rebuild removes the files of that list it no longer writes (tools/character_import.py).
"""

import argparse
import fnmatch
import io
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from character_import import tidy, write_mod_ini  # noqa: E402
import dat2  # noqa: E402
import xbt  # noqa: E402

DXT1, DXT3, DXT5 = 0x10, 0x11, 0x12
COLOUR_AT = {DXT1: 0, DXT3: 8, DXT5: 8}  # where a block's colour half starts
BLOCK = {DXT1: 8, DXT3: 16, DXT5: 16}
TINTS = ("StartColor", "EndColor")
PARTICLES = re.compile(rb'<Particles Name="([^"]*)"(.*?)</Particles>', re.S)
PARAMS = re.compile(rb"<Params [^>]*/>")


# --- the colour map --------------------------------------------------------------------------------------


class Colour:
    """out = m + (r - m) * T with m = (g + b) / 2, taking "from" to "to" (0..255)"""

    def __init__(self, spec):
        r, g, b = spec["from"]
        m = (g + b) / 2
        if r - m < 1:
            raise SystemExit(f"error: colour {spec}: 'from' must be a red (red above green and blue)")
        self.t = tuple((c - m) / (r - m) for c in spec["to"])
        self.spec = spec

    def apply(self, rgb, top=255.0):
        r, g, b = rgb
        m = (g + b) / 2
        return tuple(min(top, max(0.0, m + (r - m) * t)) for t in self.t)


# --- DXT blocks ------------------------------------------------------------------------------------------


def unpack565(v):
    r, g, b = v >> 11, (v >> 5) & 0x3F, v & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def pack565(rgb):
    r, g, b = (round(c) for c in rgb)
    return (round(r * 31 / 255) << 11) | (round(g * 63 / 255) << 5) | round(b * 31 / 255)


SWAP4 = (1, 0, 3, 2)  # four-colour palette with the endpoints swapped: c0 <-> c1, 2/3 c0 + 1/3 c1 <-> the other
SWAP3 = (1, 0, 2, 3)  # three-colour: the midpoint and transparent black stay


def remap(indices, table):
    out = 0
    for k in range(16):
        out |= table[(indices >> (2 * k)) & 3] << (2 * k)
    return out


def recolour_block(block, at, colour, four_colour_always):
    """a DXT block with its colour endpoints mapped; the endpoints' order (which decides DXT1's mode) is
    kept, swapping them back with their indices when the map turned it round"""
    c0, c1, idx = struct.unpack_from("<HHI", block, at)
    n0, n1 = (pack565(colour.apply(unpack565(c))) for c in (c0, c1))
    four = four_colour_always or c0 > c1
    if c0 > c1:
        if n0 < n1:
            n0, n1, idx = n1, n0, remap(idx, SWAP4)
        elif n0 == n1:
            idx = 0  # all four entries are this one colour; index 0 reads it in either mode
    elif c0 < c1 and n0 > n1:
        n0, n1, idx = n1, n0, remap(idx, SWAP4 if four else SWAP3)
    elif c0 < c1 and n0 == n1 and four:
        idx = 0
    out = bytearray(block)
    struct.pack_into("<HHI", out, at, n0, n1, idx)
    return bytes(out)


def recolour_xbt(b, colour):
    """an .xbt (DXT1, DXT3 or DXT5, any mips and faces) with every block's colour endpoints mapped"""
    w, h, size, fmt, mips, faces = xbt.header(b)
    if fmt not in BLOCK:
        raise SystemExit(f"error: texture format {fmt:#x} is not DXT1, DXT3 or DXT5")
    out = bytearray(b)
    for face in range(faces):
        at = 32 + face * xbt.face_stride(fmt, w, h, mips)
        for level in range(mips):
            n = xbt.level_size(fmt, w, h, level)
            for p in range(at, at + n, BLOCK[fmt]):
                out[p : p + BLOCK[fmt]] = recolour_block(
                    bytes(out[p : p + BLOCK[fmt]]), COLOUR_AT[fmt], colour, fmt != DXT1
                )
            at += n
    return bytes(out)


# --- the particle library -------------------------------------------------------------------------------


def reddish(rgb):
    r, g, b = rgb
    return r >= 0.1 and g <= r / 3 and b <= r / 3


def number(v):
    s = f"{v:.6g}"
    return "0" if s in ("-0", "0") else s


def tint(rgb, colour):
    """a particle tint (0..1) through the colour map"""
    return tuple(c / 255 for c in colour.apply(tuple(255 * c for c in rgb)))


SCALED = (("Size", "size"), ("SizeSpeed", "size"), ("Count", "count"), ("Speed", "speed"), ("LifeTime", "life"))


def attribute(tag, name):
    return re.search(rb"\b" + name.encode() + rb'="([^"]*)"', tag)


def edit_particles(xml, tints=None, spray=None):
    """(the particle library with the named libraries' reddish tints in their colours ({library: Colour}) and
    the spray libraries' emitters scaled, [(what, old, new)] for every value changed)"""
    tints, spray = tints or {}, spray or {}
    sprayed = set(spray.get("libraries", ()))
    texture = spray.get("texture", "").lower().encode()
    out, changes, at, lib = bytearray(), [], 0, None
    # effects nest (<Childs>), but a match from one <Particles Name= to the next </Particles> still visits
    # every <Params> once, and a child's name has no library part
    for m in PARTICLES.finditer(xml):
        name = m.group(1).decode("latin-1")
        if "." in name:  # the first effect of a library names it: <library>.<effect>
            lib = name.split(".")[0]
        if lib not in tints and lib not in sprayed:
            continue
        out += xml[at : m.start(2)]
        body, pos = m.group(2), 0
        for p in PARAMS.finditer(body):
            out += body[pos : p.start()]
            tag = p.group()
            what = f"{lib}: {name.split('.')[-1]}"
            if lib in tints:
                for attr in TINTS:
                    a = attribute(tag, attr)
                    rgb = tuple(float(x) for x in a.group(1).split(b",")) if a else None
                    if rgb and len(rgb) == 3 and reddish(rgb):
                        new = tint(rgb, tints[lib])
                        changes.append((f"{what} {attr}", rgb, new))
                        tag = tag[: a.start(1)] + ",".join(number(c) for c in new).encode() + tag[a.end(1) :]
            if lib in sprayed and b'Active="1"' in tag and texture and texture in tag.lower():
                for attr, factor in SCALED:
                    a = attribute(tag, attr)
                    old = float(a.group(1))
                    v = old * spray[factor]
                    text = str(max(1, round(v))) if attr == "Count" else number(v)
                    changes.append((f"{what} {attr}", old, float(text)))
                    tag = tag[: a.start(1)] + text.encode() + tag[a.end(1) :]
            out += tag
            pos = p.end()
        out += body[pos:]
        at = m.end(2)
    out += xml[at:]
    return bytes(out), changes


def recolour_tints(xml, libraries, colour):
    """the reddish tints of the named libraries in one colour (edit_particles)"""
    return edit_particles(xml, {lib: colour for lib in libraries})


# --- the hit decal (particles/materials.dat) -------------------------------------------------------------

MATERIALS = "particles/materials.dat"
FLESH_DECAL = 6  # the decal index of GFX_Decal_Bullet_Hit_Flesh_A (the XBE's decal table)
ENTRY = 0x70


def resize_stains(b, materials, size, variance):
    """materials.dat with the hit decal of the given materials sized size +- variance (metres)"""
    magic, version, n = struct.unpack_from("<4sII", b, 0)
    if magic != b"FTAM" or version != 1 or len(b) != 12 + n * ENTRY:
        raise SystemExit("error: not a material list (FTAM, version 1)")
    out = bytearray(b)
    for i in materials:
        at = 12 + i * ENTRY
        if not 0 <= i < n or struct.unpack_from("<i", b, at + 0xC)[0] != FLESH_DECAL:
            raise SystemExit(f"error: material {i} does not leave the flesh decal")
        struct.pack_into("<f", out, at + 0x10, size)
        struct.pack_into("<f", out, at + 0x60, variance)
    return bytes(out)


# --- the config ------------------------------------------------------------------------------------------


def norm(path):
    return path.replace("\\", "/").strip("/")


def particle_library(rel):
    """the particle library's path in a level archive (levels/<level>/<archive>): named after the level"""
    level = Path(rel).parent.name
    return f"levels/{level}/{level}_DepLoadParticles.xml"


class Game:
    """the game's level archives, read only"""

    def __init__(self, folder):
        self.folder = Path(folder)
        if not self.folder.is_dir():
            raise SystemExit(f"error: no game folder {self.folder}")
        self.indexes = {}
        for fat in sorted(self.folder.glob("levels/*/*.fat")):
            rel = fat.relative_to(self.folder).with_suffix("").as_posix()
            self.indexes[rel] = {h: (o, s) for o, s, h in dat2.index(fat.read_bytes())}

    def archives(self, patterns):
        return [r for r in self.indexes if not patterns or any(fnmatch.fnmatch(r.lower(), p.lower()) for p in patterns)]

    def read(self, rel, path):
        at = self.indexes.get(rel, {}).get(dat2.name_hash(path))
        if at is None:
            return None
        with open(self.folder / (rel + ".dat"), "rb") as f:
            f.seek(at[0])
            return f.read(at[1])


SHARED = ("archives", "textures", "spray", "stains", "tints", "group", "credit")


def load(path):
    path = Path(path)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    colours = {k: Colour(v) for k, v in cfg["colours"].items()}
    mods = {}
    for mid, m in cfg["mods"].items():
        m = {**{k: cfg[k] for k in SHARED if k in cfg}, **m}
        named = [m.get("colour"), *m.get("levels", {}).values(), *(m.get("tints") or {}).values()]
        for c in named:
            if c is not None and c not in colours:
                raise SystemExit(f"error: {mid}: no colour {c!r} in the config's colours")
        mods[mid] = m
    return cfg, base, colours, mods


def plan(game, base, mods):
    """{mod: {(archive, path): job}} for every file each mod writes; a job is ("texture", bytes, colour),
    ("particles", bytes, {library: colour}, spray) or ("materials", bytes, stains)"""
    out, splats = {}, {}
    for mid, m in mods.items():
        files = {}
        spray, stains, tints = m.get("spray"), m.get("stains"), m.get("tints") or {}
        splat = None
        if stains and stains.get("splat"):
            src = stains["splat"]
            key = (str(base / src["game"]), src["archive"], src["path"])
            if key not in splats:
                splats[key] = Game(key[0]).read(src["archive"], src["path"])
            splat = splats[key]
            if splat is None:
                raise SystemExit(f"error: {mid}: no splat {src['path']} in {src['archive']}")
        for rel in game.archives(m.get("archives")):
            colour = m.get("colour")
            for pattern, c in m.get("levels", {}).items():
                if fnmatch.fnmatch(rel.lower(), pattern.lower()):
                    colour = c
            if colour is not None:
                for t in m.get("textures") or []:
                    b = game.read(rel, t)
                    if b is not None:
                        files[(rel, norm(t))] = ("texture", b, colour)
            lib = particle_library(rel)
            b = game.read(rel, lib)
            here = {k: v for k, v in tints.items() if b is not None and f'Name="{k}.'.encode() in b}
            if b is not None and (here or spray):
                files[(rel, lib)] = ("particles", b, here, spray)
            if stains:
                b = game.read(rel, MATERIALS)
                if b is not None:
                    files[(rel, MATERIALS)] = ("materials", b, stains)
                if splat is not None and game.read(rel, stains["texture"]) is not None:
                    files[(rel, norm(stains["texture"]))] = ("texture", splat, colour)
        if not files:
            raise SystemExit(f"error: {mid} writes nothing: none of its archives holds its files")
        out[mid] = files
    check_sets(out, mods)
    return out


def check_sets(planned, mods):
    """mods of different sets must not write one file"""
    ids = list(planned)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if mods[a].get("set", "blood") == mods[b].get("set", "blood"):
                continue
            both = set(planned[a]) & set(planned[b])
            if both:
                raise SystemExit(
                    f"error: {a} and {b} are not alternatives (other sets) but both write {'/'.join(sorted(both)[0])}"
                )


def make(job, colours):
    """(the bytes a job writes, [(what, old, new)])"""
    kind, b = job[0], job[1]
    if kind == "texture":
        return (b if job[2] is None else recolour_xbt(b, colours[job[2]])), []
    if kind == "particles":
        return edit_particles(b, {lib: colours[c] for lib, c in job[2].items()}, job[3])
    st = job[2]
    return resize_stains(b, st["materials"], st["size"], st["variance"]), [("stains", st["size"], st["variance"])]


# --- swatches --------------------------------------------------------------------------------------------


def image(b):
    from PIL import Image

    return Image.open(io.BytesIO(xbt.to_dds(b))).convert("RGBA")


def swatches(rows, names, path):
    """a sheet: a row per texture or tint, the original then each colour, over grey"""
    from PIL import Image, ImageDraw

    cell, label = 128, 220
    sheet = Image.new("RGB", (label + cell * (1 + len(names)), 20 + cell * len(rows)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for k, n in enumerate(["original", *names]):
        d.text((label + k * cell + 4, 4), n, fill=(230, 230, 230))
    for r, (title, cells) in enumerate(rows):
        y = 20 + r * cell
        d.text((4, y + 4), title, fill=(230, 230, 230))
        for k, im in enumerate(cells):
            back = Image.new("RGBA", (cell, cell), (128, 128, 128, 255))
            if isinstance(im, tuple):  # a tint: the colour itself
                back.paste(tuple(round(c * 255) for c in im) + (255,), (8, 8, cell - 8, cell - 8))
            else:
                big = im.resize((cell, cell), Image.NEAREST)
                back.alpha_composite(big)
            sheet.paste(back.convert("RGB"), (label + k * cell, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return path


def check_sheets(planned, colours, folder, game_name):
    """the original of every recoloured texture and tint, and each colour the mods give it"""
    textures, tints = {}, {}  # (path, source bytes) -> colours; tint -> colours
    for files in planned.values():
        for (_rel, path), job in files.items():
            if job[0] == "texture" and job[2] is not None:
                textures.setdefault((path, job[1]), set()).add(job[2])
            elif job[0] == "particles":
                for lib, c in job[2].items():
                    for _what, old, _new in recolour_tints(job[1], {lib}, colours[c])[1]:
                        tints.setdefault(old, set()).add(c)
    names = sorted({c for cs in textures.values() for c in cs} | {c for cs in tints.values() for c in cs})
    unused = (0.16, 0.16, 0.16)
    rows = []
    for (path, b), used in sorted(textures.items(), key=lambda kv: kv[0][0]):
        cells = [image(b)] + [image(recolour_xbt(b, colours[c])) if c in used else unused for c in names]
        rows.append((Path(path).name, cells))
    for rgb, used in sorted(tints.items()):
        cells = [rgb] + [tint(rgb, colours[c]) if c in used else unused for c in names]
        rows.append((f"tint {','.join(number(x) for x in rgb)}", cells))
    return swatches(rows, names, Path(folder) / f"blood-{game_name}.png")


# --- the run ---------------------------------------------------------------------------------------------


def build(config, only=(), check=None, dry_run=False):
    cfg, base, colours, mods = load(config)
    game = Game(base / cfg["game"])
    planned = plan(game, base, {k: v for k, v in mods.items() if not only or k in only})
    root = base / cfg["out"]
    cache = {}
    for mid, files in planned.items():
        out = root / mid
        written, counts = [], {}
        for (rel, path), job in sorted(files.items()):
            key = (job[0], hash(job[1]), json.dumps(job[2:], sort_keys=True))
            if key not in cache:
                cache[key] = make(job, colours)
            data, changes = cache[key]
            for what, _old, _new in changes:
                kind = what.split()[-1]
                counts[kind] = counts.get(kind, 0) + 1
            target = out / rel / path
            written.append(target)
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != data:
                    target.write_bytes(data)
        archives = len({rel for rel, _ in files})
        extra = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        print(f"{mid}: {len(files)} files in {archives} archives{', ' + extra if extra else ''}")
        if not dry_run:
            m = mods[mid]
            write_mod_ini(out, {k: m.get(k) for k in ("name", "group", "description", "credit")})
            tidy(out, written)
    if check:
        print("swatches:", check_sheets(planned, colours, Path(check), Path(cfg["out"]).name or "game"))
    return planned


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config")
    ap.add_argument("mods", nargs="*")
    ap.add_argument("--check", help="a folder for before/after swatches")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    build(a.config, a.mods, a.check, a.dry_run)


if __name__ == "__main__":
    main()
