# Models (.xbg)

Started 2026-10-29 on Instincts' first-person Beretta (`animations\weapons\first\beretta\beretta_first.xbg`,
rigid) and a soldier (`animations\characters\mercenaire\specops01.xbg` in `01_Beach`, skinned); the weapons
were worked out on 2026-10-30 on the MP5 (`mp5n_first.xbg`, `mp5n_3rd.xbg`) of both games. tools/xbg.py
reads them, exports .obj and rebuilds a rigid model with new geometry; tools/weapon_import.py puts a glTF
model in place of a weapon. Skinned vertices are not placed yet.

## Header

Byte 0 is the version (0 Instincts, 1 Evolution), then `09 01 01`, 0, -1, `0x4A00`, then (offset, count)
pairs and floats. Unused space in a model is filled with `CD` (an uninitialised debug heap).

| At | MP5 (first person) | |
|---|---|---|
| 0x10 | 0xB0, 1 | materials, 0x38 bytes each (not mapped; the MP5's names texture 0 and 1) |
| 0x18 | 0xF0, 2 | textures, 8 bytes each: the path's offset in the string table, 0 |
| 0x20 | 0x194, 3 | bones: a 4-byte 0, then 0x48 bytes each (below) |
| 0x28 | -1, 0 | |
| 0x30 | 0x270, 3 | bone lookup, 8 bytes each: a name hash, the bone number twice (u16), sorted by hash |
| 0x38 | 0x290, 3 | parts, 0x30 bytes each (below) |
| 0x40 | 0x330, 1 | submesh table (below) |
| 0x48 | 0x3A0, 0x6710 | vertex and index data: offset, size |
| 0x58 | 0x6AC0, 0 | the end: four zero bytes, 32-byte aligned after the data |
| 0x60 | 0, 0x62 | |
| 0x68 | 0x104, 0x56 | string table: the texture paths (their size), then the bone names, then them again in upper case |
| 0x70 | | bounding box: min, max of x, then of y, then of z |
| 0x88 | | bounding sphere: centre, radius |
| 0x9C | 1/32767 | position scale (0.002 in the Beretta and the third-person models) |
| 0xA0 | 0.5, 1/65536 | texture coordinate offset and scale |

A bone: first child, next sibling, parent (-1 for none), rotation (x, y, z, w), position, scale (3 floats
each), -1, 1.0, a u16 0xFF and the u16 offset of its name in the string table, 0, a hash. The MP5's bones:
`B_FRAME` at the origin, `b_Magazine` at (0.218, 0.034, 0.034) and `b_Slide` (the cocking handle) at
(0.349, 0.055, 0.143), both children of the frame, no rotation.

A part (one per bone in the weapons): its triangle count, its bone, its submesh's vertex offset, 0,
`0x00010001`, a bounding sphere (centre in the bone's frame, radius), the offset of the bone's upper-case
name, then -1 and 0 in Instincts, 0 and 0 in Evolution (the only other difference between the two games'
MP5 models besides the version byte).

## Submeshes

Nine ints each, until one does not start `FFFF`: `FFFF` + material index, vertex offset and index offset
(both from the data start), stride << 16 | index count, a vertex tag << 16 | vertex count (`53BF` with
tangents, `5D91` without), eight bone palette bytes (FF in the rigid ones), zeros. Each submesh's vertices
start 32-byte aligned (CD between), its indices follow them directly. Indices are 16-bit triangle strips;
degenerate triangles join the walks. Seen from the front a triangle's vertices go clockwise: for an even
triangle of the strip (a, b, c), cross(b - a, c - a) points away from its normals (Direct3D's default).

## Vertices

Positions are int16 times the position scale, followed by an int16 1; texture coordinates int16 * 1/65536 +
0.5 (v down the image, as in Direct3D). Directions are D3DCOLORs: bytes z, y, x around 128 ((b - 128) / 127),
then 128.

| Size | Seen in | After position and uv |
|---|---|---|
| 24 | first-person weapons | normal, tangent (+u), binormal (-v, up the image) |
| 16 | third-person weapons | normal |
| 28 | characters | 4 bytes that look like two weights (bytes adding up to 255) and two palette slots times 4, then normal, tangent, binormal; positions about +-1 at 1/32767, relative to something (bones or another scale): open |

Checked on the MP5's 664 frame triangles: the normals agree with the faces (0.97), the tangents with +u
(0.98) and the binormals with -v (0.97), each only in the z, y, x byte order.

The weapons are rigid: each part's vertices are in its bone's frame (the MP5's magazine around its bone's
origin; placed by its bone the model's box is the header's to the float). The animations move the bones.
Units are metres, X is the muzzle, Z up; the third-person MP5 has the first-person one's size and
place, so one placement serves both.

## Textures of a weapon

The MP5: `mp5n_df` 256x256 DXT3 (alpha 153-221: gloss), `mp5n_nt` 256x256 DXT1 normal map, `mp5n_3rd`
128x128 DXT5 (alpha 123-255), no mip levels. The normal maps are DirectX style, green pointing down the
image (+v): on every weapon checked (MP5, Beretta, M16, P90) the green channel's change across correlates
positively with the red channel's change down (an OpenGL map, green up, correlates negatively).

## Importing a glTF (tools/weapon_import.py)

The template is the weapon's own model: materials, textures, bones and parts stay, each part's submesh gets
the pieces (connected parts of the glTF mesh) chosen for its bone, in the bone's frame. All materials go
into one atlas (diffuse with gloss from 1 - roughness as alpha, DXT5; normal map DXT1; all mip levels).
The binormals are made to point along -v whatever the glTF's tangents say; the normal maps' green is
flipped from the glTF standard (up) unless the model's are DirectX style already.

First weapon: the Halo MA5B (Sketchfab "MA5B Remaster", CC-BY-4.0) in place of the MP5. Its pistol grip
was put on the MP5's (centre about (0.082, 0.034, 0) in the frame), 2.2 mm per glTF unit; barrel height,
length and handguard then land on the MP5's. 26,114 of its 36,400 triangles are cartridges inside the
magazine and the chamber and are left out; it has no separate magazine, so `b_Magazine` and `b_Slide`
get a placeholder triangle.
