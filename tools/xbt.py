"""The games' textures (.xbt in the DAT2 archives) to and from .dds (re/notes/ARCHIVES.md).

  python -B tools/xbt.py todds <in.xbt> [<out.dds>]
  python -B tools/xbt.py fromdds <in.dds> [<out.xbt>]

An .xbt is a 32-byte header (MAGIC, width, height, data size, format, mip levels, faces, 0) and the data:
each face (6 for a cube map, each starting 128-byte aligned) with all its levels, largest first. DXT1, DXT3
and DXT5 are stored as on the PC; the uncompressed formats are swizzled (Morton order, each level by
itself). Formats this tool does not know yet (two 16-bit ones and 0x0a) are refused, not guessed.
"""

import argparse
from pathlib import Path
import struct

MAGIC = b"\x00\x01\x04\x03"
# format: (name, bytes per 4x4 block or 0, bytes per pixel or 0)
FORMATS = {
    0x10: ("DXT1", 8, 0),
    0x11: ("DXT3", 16, 0),
    0x12: ("DXT5", 16, 0),
    0x0E: ("L8", 0, 1),  # bump and height maps (the characters' _nt)
    0x0C: ("A8R8G8B8", 0, 4),
}
FOURCC = {"DXT1": 0x10, "DXT3": 0x11, "DXT5": 0x12}
MASKS_ARGB = (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)

# DDS header flags
DDSD = 0x1 | 0x2 | 0x4 | 0x1000  # caps, height, width, pixel format
DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x20000, 0x80000
DDPF_ALPHAPIXELS, DDPF_FOURCC, DDPF_RGB, DDPF_LUMINANCE = 0x1, 0x4, 0x40, 0x20000
CAPS_COMPLEX, CAPS_TEXTURE, CAPS_MIPMAP = 0x8, 0x1000, 0x400000
CAPS2_CUBEMAP_ALL = 0x200 | 0xFC00
FACE_ALIGN = 128


def level_size(fmt, w, h, level):
    _, block, pixel = FORMATS[fmt]
    w, h = max(1, w >> level), max(1, h >> level)
    if block:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    return w * h * pixel


def face_size(fmt, w, h, mips):
    return sum(level_size(fmt, w, h, i) for i in range(mips))


def face_stride(fmt, w, h, mips):
    """a cube map's faces start 128-byte aligned; the padding is not in a .dds"""
    return (face_size(fmt, w, h, mips) + FACE_ALIGN - 1) // FACE_ALIGN * FACE_ALIGN


def data_size(fmt, w, h, mips, faces):
    return (faces - 1) * face_stride(fmt, w, h, mips) + face_size(fmt, w, h, mips)


def header(b):
    """(width, height, data size, format, mips, faces) of an .xbt"""
    if not b.startswith(MAGIC) or len(b) < 32:
        raise ValueError("not an .xbt")
    return struct.unpack_from("<6I", b, 4)


def morton(w, h):
    """for each pixel in rows, its place in the swizzled level: x and y bits interleaved, x first, while each
    side still has bits"""
    xbits, ybits, bit, i = [], [], 0, 0
    while (1 << i) < max(w, h):
        if (1 << i) < w:
            xbits.append(bit)
            bit += 1
        if (1 << i) < h:
            ybits.append(bit)
            bit += 1
        i += 1
    xs = [sum(((x >> i) & 1) << b for i, b in enumerate(xbits)) for x in range(w)]
    ys = [sum(((y >> i) & 1) << b for i, b in enumerate(ybits)) for y in range(h)]
    return [ys[y] | xs[x] for y in range(h) for x in range(w)]


def swizzle(data, w, h, pixel, unswizzle=False):
    order = morton(w, h)
    out = bytearray(len(data))
    for linear, swz in enumerate(order):
        src, dst = (swz, linear) if unswizzle else (linear, swz)
        out[dst * pixel : dst * pixel + pixel] = data[src * pixel : src * pixel + pixel]
    return bytes(out)


def levels(fmt, w, h, mips, faces, data, to_dds):
    """.xbt data as .dds data (unswizzled, no face padding) or back"""
    _, block, pixel = FORMATS[fmt]
    size, stride = face_size(fmt, w, h, mips), face_stride(fmt, w, h, mips)
    out = bytearray()
    for face in range(faces):
        at = face * (stride if to_dds else size)
        if not to_dds and face:
            out += bytes(stride - size)
        for i in range(mips):
            n = level_size(fmt, w, h, i)
            level = data[at : at + n]
            out += level if block else swizzle(level, max(1, w >> i), max(1, h >> i), pixel, unswizzle=to_dds)
            at += n
    return bytes(out)


def to_dds(b):
    w, h, size, fmt, mips, faces = header(b)
    if fmt not in FORMATS:
        raise ValueError(f"format 0x{fmt:02x} is not known yet")
    if size != data_size(fmt, w, h, mips, faces) or len(b) < 32 + size:
        raise ValueError("the data does not fit the header")
    name, block, pixel = FORMATS[fmt]
    if block:
        pf = struct.pack("<II4s5I", 32, DDPF_FOURCC, name.encode(), 0, 0, 0, 0, 0)
    elif name == "L8":
        pf = struct.pack("<II4s5I", 32, DDPF_LUMINANCE, b"\0" * 4, 8, 0xFF, 0, 0, 0)
    else:
        pf = struct.pack("<II4s5I", 32, DDPF_RGB | DDPF_ALPHAPIXELS, b"\0" * 4, 32, *MASKS_ARGB)
    caps = CAPS_TEXTURE | (CAPS_COMPLEX | CAPS_MIPMAP if mips > 1 else 0) | (CAPS_COMPLEX if faces == 6 else 0)
    hdr = struct.pack(
        "<7I44s32s4I4x",
        124,
        DDSD | DDSD_MIPMAPCOUNT | DDSD_LINEARSIZE,
        h,
        w,
        level_size(fmt, w, h, 0),
        0,
        mips,
        b"\0" * 44,
        pf,
        caps,
        CAPS2_CUBEMAP_ALL if faces == 6 else 0,
        0,
        0,
    )
    return b"DDS " + hdr + levels(fmt, w, h, mips, faces, b[32 : 32 + size], to_dds=True)


def from_dds(dds, like=None):
    """an .xbt of a .dds (DXT1, DXT3, DXT5, 8-bit luminance or 32-bit ARGB/XRGB, legacy header); like is the
    .xbt it replaces, if any, kept for the caller's checks"""
    if dds[:4] != b"DDS " or len(dds) < 128:
        raise ValueError("not a .dds")
    flags, h, w = struct.unpack_from("<III", dds, 8)
    mips = struct.unpack_from("<I", dds, 28)[0] if flags & DDSD_MIPMAPCOUNT else 1
    pf_flags, fourcc, bits, *masks = struct.unpack_from("<I4s5I", dds, 80)
    caps2 = struct.unpack_from("<I", dds, 112)[0]
    faces = 6 if caps2 & 0x200 else 1
    if faces == 6 and caps2 & CAPS2_CUBEMAP_ALL != CAPS2_CUBEMAP_ALL:
        raise ValueError("a cube map needs all six faces")
    mips = max(1, mips)
    alpha = True
    if pf_flags & DDPF_FOURCC:
        if fourcc == b"DX10":
            raise ValueError("save it with a legacy DDS header (DXT1, DXT3 or DXT5), not DX10/BC")
        fmt = FOURCC.get(fourcc.decode("latin-1"))
        if fmt is None:
            raise ValueError(f"{fourcc!r} is not DXT1, DXT3 or DXT5")
    elif pf_flags & DDPF_LUMINANCE and bits == 8 and not pf_flags & DDPF_ALPHAPIXELS:
        fmt = 0x0E
    elif pf_flags & DDPF_RGB and bits == 32 and tuple(masks[:3]) == MASKS_ARGB[:3]:
        fmt, alpha = 0x0C, bool(pf_flags & DDPF_ALPHAPIXELS and masks[3] == MASKS_ARGB[3])
    else:
        raise ValueError("an uncompressed .dds must be 8-bit luminance or 32-bit A8R8G8B8 / X8R8G8B8")
    if not FORMATS[fmt][1] and (w & (w - 1) or h & (h - 1)):
        raise ValueError(f"{w}x{h}: uncompressed textures must be a power of two on each side")
    size = faces * face_size(fmt, w, h, mips)
    data = dds[128 : 128 + size]
    if len(data) != size:
        raise ValueError("the .dds is shorter than its header says")
    if not alpha:
        data = bytes(v if i % 4 != 3 else 0xFF for i, v in enumerate(data))
    data = levels(fmt, w, h, mips, faces, data, to_dds=False)
    return MAGIC + struct.pack("<7I", w, h, len(data), fmt, mips, faces, 0) + data


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("todds", "fromdds"))
    ap.add_argument("source")
    ap.add_argument("target", nargs="?")
    a = ap.parse_args()
    src = Path(a.source)
    dst = Path(a.target) if a.target else src.with_suffix(".dds" if a.command == "todds" else ".xbt")
    try:
        dst.write_bytes((to_dds if a.command == "todds" else from_dds)(src.read_bytes()))
    except ValueError as e:
        raise SystemExit(f"error: {src}: {e}")
    print(dst)


if __name__ == "__main__":
    main()
