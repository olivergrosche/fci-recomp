"""The games' DAT2 archives (lua, common, weaponpack, farcryed, the levels', the sound banks): list them,
take files out and put changed files back (re/notes/ARCHIVES.md).

  python -B tools/dat2.py list <archive> [--game <folder>]
  python -B tools/dat2.py extract <archive> <folder> [--game <folder>] [--dds]
  python -B tools/dat2.py replace <archive> <folder> [--dry-run]
  python -B tools/dat2.py restore <archive>

  <archive>   the .dat or .fat (or the name without either), e.g. FarCryInstincts/game/weaponpack.dat
  --game      the game's files (its game/ folder), searched for file names; by default the archive's own
              folder and the one above it
  --dds       also write textures as .dds next to their .xbt (tools/xbt.py)

An archive stores no names, only a hash of each: the CRC-32 of the path in lower case, with \\ and a
leading \\ (\\animations\\weapons\\first\\beretta\\beretta_first.xbg). Names are found as strings in the
game's files and scripts; a file nobody names is extracted as _unnamed/<hash>.<type>.

replace puts every file under <folder> into the archive in place of the file with the same path:
animations/weapons/first/beretta/handguns_beretta92fs_df.xbt, or a .dds there, converted to the .xbt it
replaces. A path the archive does not have is added. The first run keeps the original as .dat.orig and
.fat.orig and every run starts from them, so runs don't stack. Close the game first.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbt  # noqa: E402

PATH = re.compile(rb"[A-Za-z0-9_\\/ .-]{2,200}\.(?:xbt|xbg|xba|mrg\.bin|lua|dds|xml|tga|wav|xpr|ini|txt)", re.I)
TYPES = (  # file type from its first bytes, for files without a name
    (xbt.MAGIC, "xbt"),
    (b"\x00\x09\x01\x01", "xbg"),
    (b"ubi/b0-l", "mrg.bin"),
    (b"\x1bLua", "lua"),
    (b"DDS ", "dds"),
    (b"<?xml", "xml"),
    (b"#", "xba"),
)


def key(path):
    """an archive's name for path: lower case, backslashes, one leading backslash"""
    return "\\" + path.replace("/", "\\").strip().lstrip("\\").lower()


def name_hash(path):
    return zlib.crc32(key(path).encode("latin-1")) & 0xFFFFFFFF


def paths(archive):
    """(.dat, .fat) of an archive given by either file or its name without them"""
    p = Path(archive)
    if p.suffix.lower() in (".dat", ".fat"):
        p = p.with_suffix("")
    return p.with_name(p.name + ".dat"), p.with_name(p.name + ".fat")


def index(fat):
    """(offset, size, name hash) of each file, in the archive's order (by hash)"""
    if fat[:4] != b"DAT2":
        raise ValueError("not a DAT2 index")
    n = struct.unpack_from("<I", fat, 4)[0]
    if len(fat) != 8 + 12 * n:
        raise ValueError("a DAT2 index of the wrong length")
    return [struct.unpack_from("<III", fat, 8 + 12 * i) for i in range(n)]


def read(archive, orig=False):
    """{name hash: bytes} in the order the files lie in the .dat; with orig, of the kept original"""
    dat, fat = originals(archive) if orig else paths(archive)
    data = dat.read_bytes()
    return {h: data[o : o + s] for o, s, h in sorted(index(fat.read_bytes()))}


def originals(archive):
    dat, fat = paths(archive)
    return dat.with_name(dat.name + ".orig"), fat.with_name(fat.name + ".orig")


def build(files):
    """(.dat, .fat) bytes for {name hash: bytes}: the data in the dict's order, the index sorted by hash"""
    dat, at = bytearray(), {}
    for h, b in files.items():
        at[h] = (len(dat), len(b))
        dat += b
    fat = b"DAT2" + struct.pack("<I", len(files)) + b"".join(struct.pack("<III", *at[h], h) for h in sorted(at))
    return bytes(dat), fat


def known_names(folders):
    """{name hash: path} for every path named in the files of folders (.dat, .xbe, .xml, ...), recursively"""
    names = {}
    for folder in folders:
        for f in sorted(Path(folder).rglob("*")):
            if not f.is_file() or f.suffix.lower() in (".orig", ".bik", ".xwb") or "sound" in f.name.lower():
                continue
            for m in PATH.findall(f.read_bytes()):
                text = m.decode("latin-1")
                # a path may follow other words: try it from each space on too
                for path in [text] + [text[i + 1 :] for i, c in enumerate(text) if c == " "]:
                    if path.strip():
                        names.setdefault(name_hash(path), key(path))
    return names


def file_type(b):
    return next((t for magic, t in TYPES if b.startswith(magic)), "bin")


def out_path(folder, h, b, names):
    if h in names:
        return Path(folder, *names[h].lstrip("\\").split("\\"))
    return Path(folder, "_unnamed", f"{h:08x}.{file_type(b)}")


def extract(archive, folder, names, dds=False):
    """write the archive's files under folder; the count of files and of those without a name"""
    files = read(archive)
    unnamed = 0
    for h, b in files.items():
        p = out_path(folder, h, b, names)
        unnamed += h not in names
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
        if dds and b.startswith(xbt.MAGIC):
            try:
                p.with_suffix(".dds").write_bytes(xbt.to_dds(b))
            except ValueError as e:
                print(f"  {p.name}: no .dds ({e})")
    return len(files), unnamed


def changes(folder, files):
    """{name hash: (path in folder, new bytes)} for the files under folder; a .dds becomes the .xbt it names"""
    out = {}
    for f in sorted(Path(folder).rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(folder).as_posix()
        if rel.lower().startswith("_unnamed/"):
            h = int(f.name.split(".")[0], 16)
        elif f.suffix.lower() == ".dds":
            h = name_hash(rel[:-4] + ".xbt")
        else:
            h = name_hash(rel)
        b = f.read_bytes()
        if f.suffix.lower() == ".dds":
            b = xbt.from_dds(b, files.get(h))
        if h in out:
            raise SystemExit(f"error: {rel} and {out[h][0]} are the same file in the archive")
        out[h] = (rel, b)
    return out


def replace(archive, folder, dry_run=False):
    """put folder's files into the archive, starting from the original; (path, old size or None, new size)"""
    dat, fat = paths(archive)
    orig_dat, orig_fat = originals(archive)
    files = read(archive, orig=orig_dat.exists())
    done = []
    for h, (rel, b) in changes(folder, files).items():
        done.append((rel, len(files[h]) if h in files else None, len(b)))
        files[h] = b
    if not dry_run:
        if not orig_dat.exists():
            shutil.copy2(dat, orig_dat)
            shutil.copy2(fat, orig_fat)
        new_dat, new_fat = build(files)
        write(dat, new_dat)
        write(fat, new_fat)
    return done


def write(path, data):
    """write by replacing the file, never through it: a hard-linked game file stays as it was"""
    tmp = path.with_name(path.name + ".new")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def restore(archive):
    dat, fat = paths(archive)
    orig_dat, orig_fat = originals(archive)
    if not orig_dat.exists():
        return False
    write(dat, orig_dat.read_bytes())
    write(fat, orig_fat.read_bytes())
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("list", "extract", "replace", "restore"))
    ap.add_argument("archive")
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--game", action="append", default=[])
    ap.add_argument("--dds", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dat, fat = paths(a.archive)
    if not (dat.is_file() and fat.is_file()):
        raise SystemExit(f"error: no archive {dat} with {fat.name}")
    if a.command in ("extract", "replace") and not a.folder:
        raise SystemExit(f"error: {a.command} needs a folder")
    if a.command == "restore":
        print("the original is back" if restore(a.archive) else "unchanged: no .orig")
    elif a.command == "replace":
        for rel, old, new in replace(a.archive, a.folder, a.dry_run):
            print(f"  {rel}: " + (f"{old} -> {new} bytes" if old is not None else f"added, {new} bytes"))
    else:
        names = known_names(a.game or [dat.parent, dat.parent.parent])
        if a.command == "list":
            for h, b in read(a.archive).items():
                print(f"{h:08x} {len(b):9d}  {names.get(h, '?.' + file_type(b))}")
        else:
            n, unnamed = extract(a.archive, a.folder, names, a.dds)
            print(f"{n} files to {a.folder}, {unnamed} without a name (_unnamed)")


if __name__ == "__main__":
    main()
