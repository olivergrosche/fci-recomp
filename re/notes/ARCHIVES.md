# Archives and textures

Found 2026-10-29 from both games' files; read and written with tools/dat2.py and tools/xbt.py.

## DAT2 archives

Every `.dat` in `game/` and `game/levels/<level>/` has an index `.fat`: `DAT2`, the file count, then per
file its offset, size and name hash (three little-endian ints). The index is sorted by hash; the data in
the `.dat` lies in another order, without gaps. All 84 archives of both games are rebuilt byte for byte
from their files (`dat2.build`).

The name hash is the CRC-32 (zlib) of the path in lower case with backslashes and one leading backslash:
`\animations\weapons\first\beretta\handguns_beretta92fs_df.xbt`. The names themselves are not stored; they
are found as strings in the other files (models name their textures, `.xba` files their animations, the
scripts their models). That names all 651 files of Instincts' `weaponpack` and most of the levels'
character files; `lua` (404 scripts), most of `common` and a third of `farcryed` stay unnamed for now.

The engine takes rebuilt archives of another size: Evolution ran from the title into the first level with
a `weaponpack` 100 KB smaller and a `common` whose 414 DXT textures were changed (the HUD came out red).

| Archive | Holds |
|---|---|
| `weaponpack` | first- and third-person weapon models (`.xbg`), their textures, animations and `.xba` lists |
| `common` | HUD and menu textures, shaders, fonts, string tables |
| `farcryed` | the map editor's objects and the multiplayer maps' |
| `levels/<level>/<level>` | the level: its characters (`animations\characters\...`), objects, terrain |
| `lua` | the compiled scripts (WEAPONS.md) |
| `DVDsound`, `HDsound` | sound banks |

## Textures (.xbt)

A 32-byte header: `00 01 04 03`, width, height, data size, format, mip levels, faces (1, or 6 for a cube
map), 0. Then each face with its levels, largest first; the faces of a cube map start 128-byte aligned
(the padding holds leftovers, not zeros).

| Format | | Seen on |
|---|---|---|
| 0x10 | DXT1 | most diffuse maps, the weapons' normal maps, environment cube maps |
| 0x11 | DXT3 | |
| 0x12 | DXT5 | diffuse maps with alpha (the alpha holds the gloss on weapons) |
| 0x0E | 8-bit, swizzled | the characters' `_nt` bump maps (a height field, not a normal map) |
| 0x0C | 32-bit ARGB, swizzled | |
| 0x08, 0x13 | 16-bit, swizzled | hats' `_no` maps, cube maps; layout not known yet |
| 0x0A | | one 8x8 texture (`tvscreen_pixels`) |

DXT data is stored as on the PC (checked by eye on the Beretta's maps). Swizzled means Morton order: x
and y bits interleaved, x first, while each side still has bits, each level by itself. Every texture of a
known format converts to `.dds` and back to the same bytes (27,397 in both games; 16 cube maps differ
only in their padding).
