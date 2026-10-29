"""tools/dat2.py and tools/xbt.py on synthetic archives and textures (no game data)"""

from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dat2  # noqa: E402
import xbt  # noqa: E402


def texture(fmt, w, h, mips=1, faces=1, fill=None):
    size = xbt.data_size(fmt, w, h, mips, faces)
    data = fill if fill is not None else bytes(i * 7 % 251 for i in range(size))
    return xbt.MAGIC + struct.pack("<7I", w, h, size, fmt, mips, faces, 0) + data


def archive(folder, files):
    """an archive game/test.dat + .fat holding {path: bytes}, the data in reverse order of the index"""
    folder.mkdir(parents=True, exist_ok=True)
    dat, fat = dat2.build({dat2.name_hash(p): b for p, b in reversed(list(files.items()))})
    (folder / "test.dat").write_bytes(dat)
    (folder / "test.fat").write_bytes(fat)
    return folder / "test"


def test_name_hash_is_crc32_of_the_lowercase_backslash_path():
    assert dat2.key("Animations/Weapons/First/Beretta/X.XBT") == r"\animations\weapons\first\beretta\x.xbt"
    assert dat2.name_hash(r"\a\b.xbt") == dat2.name_hash("A/B.XBT") == dat2.name_hash(r"a\b.xbt")


def test_build_round_trips_and_sorts_the_index(tmp_path):
    files = {"a/one.xbg": b"1" * 5, "b/two.xba": b"#two", "c/three.lua": b"\x1bLua"}
    a = archive(tmp_path / "game", files)
    index = dat2.index((tmp_path / "game" / "test.fat").read_bytes())
    assert [h for _, _, h in index] == sorted(dat2.name_hash(p) for p in files)
    read = dat2.read(a)
    assert {h: b for h, b in read.items()} == {dat2.name_hash(p): b for p, b in files.items()}
    assert dat2.build(read) == (
        (tmp_path / "game" / "test.dat").read_bytes(),
        (tmp_path / "game" / "test.fat").read_bytes(),
    )


def test_extract_names_files_found_in_the_game(tmp_path):
    a = archive(
        tmp_path / "game",
        {"w/gun.xbg": b"\x00\x09\x01\x01 refers to w\\gun_df.xbt", "w/gun_df.xbt": texture(0x10, 8, 8)},
    )
    names = dat2.known_names([tmp_path / "game"])
    n, unnamed = dat2.extract(a, tmp_path / "out", names, dds=True)
    assert (n, unnamed) == (2, 1)  # nothing names gun.xbg itself
    assert (tmp_path / "out" / "w" / "gun_df.dds").read_bytes()[:4] == b"DDS "
    assert (tmp_path / "out" / "_unnamed" / f"{dat2.name_hash('w/gun.xbg'):08x}.xbg").exists()


def test_replace_keeps_the_original_and_never_stacks(tmp_path):
    a = archive(tmp_path / "game", {"w/gun.xbg": b"old", "w/other.xba": b"#other"})
    mod = tmp_path / "mod"
    (mod / "w").mkdir(parents=True)
    (mod / "w" / "gun.xbg").write_bytes(b"new and longer")
    (mod / "w" / "added.xba").write_bytes(b"#added")
    assert sorted(dat2.replace(a, mod)) == [("w/added.xba", None, 6), ("w/gun.xbg", 3, 14)]
    assert dat2.replace(a, mod)[0][1] in (None, 3)  # starts again from the .orig
    files = dat2.read(a)
    assert files[dat2.name_hash("w/gun.xbg")] == b"new and longer"
    assert files[dat2.name_hash("w/other.xba")] == b"#other"
    assert dat2.read(a, orig=True)[dat2.name_hash("w/gun.xbg")] == b"old"
    assert dat2.restore(a) and dat2.read(a)[dat2.name_hash("w/gun.xbg")] == b"old"


def test_replace_writes_a_new_file_so_hard_links_keep_the_original(tmp_path):
    a = archive(tmp_path / "orig", {"w/gun.xbg": b"old"})
    (tmp_path / "copy").mkdir()
    for ext in (".dat", ".fat"):
        (tmp_path / "copy" / ("test" + ext)).hardlink_to(tmp_path / "orig" / ("test" + ext))
    (tmp_path / "mod" / "w").mkdir(parents=True)
    (tmp_path / "mod" / "w" / "gun.xbg").write_bytes(b"new")
    dat2.replace(tmp_path / "copy" / "test", tmp_path / "mod")
    assert dat2.read(a)[dat2.name_hash("w/gun.xbg")] == b"old"
    assert dat2.read(tmp_path / "copy" / "test")[dat2.name_hash("w/gun.xbg")] == b"new"


def test_replace_converts_dds_to_the_xbt_it_names(tmp_path):
    a = archive(tmp_path / "game", {"w/gun_df.xbt": texture(0x12, 8, 8), "x/9.xbt": texture(0x10, 4, 4)})
    (tmp_path / "mod" / "w").mkdir(parents=True)
    (tmp_path / "mod" / "_unnamed").mkdir()
    new = texture(0x10, 16, 8, mips=2)
    (tmp_path / "mod" / "w" / "gun_df.dds").write_bytes(xbt.to_dds(new))
    (tmp_path / "mod" / "_unnamed" / f"{dat2.name_hash('x/9.xbt'):08x}.dds").write_bytes(xbt.to_dds(new))
    dat2.replace(a, tmp_path / "mod")
    files = dat2.read(a)
    assert files[dat2.name_hash("w/gun_df.xbt")] == files[dat2.name_hash("x/9.xbt")] == new


@pytest.mark.parametrize(
    "fmt,w,h,mips,faces",
    [
        (0x10, 64, 32, 7, 1),
        (0x11, 16, 16, 5, 1),
        (0x12, 256, 256, 9, 1),
        (0x10, 16, 16, 5, 6),
        (0x0E, 32, 8, 6, 1),
        (0x0C, 8, 16, 5, 6),
    ],
)
def test_xbt_dds_round_trip(fmt, w, h, mips, faces):
    t = texture(fmt, w, h, mips, faces)
    if faces == 6:  # the padding between faces is not in a .dds: zero it for the comparison
        size, stride = xbt.face_size(fmt, w, h, mips), xbt.face_stride(fmt, w, h, mips)
        data = bytearray(t[32:])
        for face in range(5):
            data[face * stride + size : (face + 1) * stride] = bytes(stride - size)
        t = t[:32] + bytes(data)
    dds = xbt.to_dds(t)
    assert len(dds) == 128 + faces * xbt.face_size(fmt, w, h, mips)
    assert xbt.from_dds(dds) == t


def test_cube_faces_start_128_byte_aligned():
    # a 16x16 DXT1 cube map with 5 levels: 184 bytes a face, faces 256 apart, as in the games' environment maps
    assert xbt.face_size(0x10, 16, 16, 5) == 184
    assert xbt.data_size(0x10, 16, 16, 5, 6) == 5 * 256 + 184 == 1464


def test_uncompressed_levels_are_swizzled():
    # a 4x2 L8 level: pixels in rows 0..7, stored x0y0 x1y0 x0y1 x1y1 x2y0 x3y0 x2y1 x3y1
    rows = bytes(range(8))
    stored = xbt.swizzle(rows, 4, 2, 1)
    assert stored == bytes([0, 1, 4, 5, 2, 3, 6, 7])
    assert xbt.swizzle(stored, 4, 2, 1, unswizzle=True) == rows


def test_unknown_formats_are_refused():
    with pytest.raises(ValueError, match="0x13"):
        xbt.to_dds(xbt.MAGIC + struct.pack("<7I", 4, 4, 32, 0x13, 1, 1, 0) + bytes(32))
