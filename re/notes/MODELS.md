# Models (.xbg)

Started 2026-10-29 on Instincts' first-person Beretta (`animations\weapons\first\beretta\beretta_first.xbg`,
rigid) and a soldier (`animations\characters\mercenaire\specops01.xbg` in `01_Beach`, skinned). Nothing
writes models yet; this is what is known.

## Header

`00 09 01 01`, 0, -1, `0x4A00`, then (offset, count) pairs, then floats. Unused space in a model is filled
with `CD` (an uninitialised debug heap), so sections end where the `CD` run starts.

| At | Beretta | Soldier | |
|---|---|---|---|
| 0x10 | 0xB0, 2 | 0xB0, 13 | materials, 0x38 bytes each: the Beretta's two name textures 0, 1 and 2, 3 (diffuse, normal); the rest unread |
| 0x18 | 0x120, 4 | 0x330, 15 | textures, 8 bytes each: the path's offset in the string table, 0 |
| 0x20 | 0x290, 4 | 0xA68, 57 | bones, 0x4C bytes each; seen: an identity quaternion, small offsets, 1.0 scales (fields not mapped yet) |
| 0x30 | 0x3C0, 4 | 0x2AE0, 2 | ? (12 bytes each) |
| 0x38 | 0x3F0, 4 | 0x2B00, 2 | ? 0x34 bytes each, with a bone number, a submesh's vertex offset and a bounding sphere (guess: one part per bone) |
| 0x40 | 0x4C0, 1 | 0x2B70, 1 | submesh table (below) |
| 0x48 | 0x580, size | 0x2DE0, size | vertex and index data |
| 0x68 | 0x144, 0x100 | 0x3AC, 0x336 | string table: offset, size of the texture paths; the bone names follow |
| 0x70 | | | bounding box (min, max of each axis) and sphere (centre, radius) |
| 0x9C | 0.002 | 1/32767 | position scale |
| 0xA0 | 0.5, 1/65536 | | texture coordinate offset and scale |

## Submeshes

Nine ints each, until one does not start `FFFF`: `FFFF` + material index, vertex offset and index offset
(both from the data start), stride << 16 | index count, `53BF` << 16 | vertex count, then for skinned
meshes eight bone palette bytes, then zeros. Indices are 16-bit triangle strips (degenerate triangles join
the strips); in the Beretta they fill the data exactly to its size.

## Vertices

Rigid, 24 bytes (the Beretta):

| Bytes | |
|---|---|
| 0-7 | position: x, y, z as int16 times the position scale, then 1 |
| 8-11 | texture coordinates: u, v as int16 / 65536 + 0.5 (checked: the Beretta's frame lies on its texture) |
| 12-15 | normal, 16-19 tangent, 20-23 binormal: x, y, z as bytes around 128, then 128 |

Skinned, 28 bytes (the soldier): the same, with 4 bytes after the texture coordinates that look like two
weights (bytes adding up to 255) and two palette slots times 4. Their positions span about +-1 at the
1/32767 scale and do not match the bounding box, so they are relative to something (the bones, or another
scale): open.

The Beretta has five submeshes and four bones (frame, magazine, hammer, slide); the frame's submesh holds
no slide, so the parts likely hang on the bones rigidly (to be checked against the 0x38 table).
