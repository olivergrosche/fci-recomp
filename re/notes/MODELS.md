# Models (.xbg)

Started 2026-10-29 on Instincts' first-person Beretta (`animations\weapons\first\beretta\beretta_first.xbg`,
rigid) and a soldier (`animations\characters\mercenaire\specops01.xbg` in `01_Beach`, skinned); the weapons
were worked out on 2026-10-30 on the MP5 (`mp5n_first.xbg`, `mp5n_3rd.xbg`) of both games, the skinned
characters the same day on all 546 models under `animations\characters\` of both games (CHARACTERS.md).
tools/xbg.py reads them, places rigid and skinned vertices, exports .obj and rebuilds a rigid model or a
character with new geometry; tools/weapon_import.py puts a glTF model in place of a weapon.

## Header

Byte 0 is the version (0 Instincts, 1 Evolution), then `09 01 01`, 0, -1, `0x4A00`, then (offset, count)
pairs and floats. Unused space in a model is filled with `CD` (an uninitialised debug heap). The blocks
follow in this order: materials, textures, strings, bones, ragdoll, skin matrices, part index, parts,
submesh table, data, tail.

| At | MP5 (first person) | Soldier (specops01) | |
|---|---|---|---|
| 0x10 | 0xB0, 1 | 0xB0, 13 | materials, 0x30 bytes each (below) |
| 0x18 | 0xF0, 2 | 0x330, 15 | textures, 8 bytes each: the path's offset in the string table, 0 |
| 0x20 | 0x194, 3 | 0xA68, 57 | bones: a 4-byte 0, then 0x48 bytes each (below) |
| 0x28 | -1, 0 | 0x1D1C, 55 | skin matrices, 0x40 bytes each (below) |
| 0x30 | 0x270, 3 | 0x2AE0, 2 | part index, 8 bytes per part, in part order: the CRC-32 of the part's name, the part and its bone (u16 each, 0xFFFF for a skinned part) |
| 0x38 | 0x290, 3 | 0x2B00, 2 | parts, 0x30 bytes each (below) |
| 0x40 | 0x330, 1 | 0x2B70, 1 | submesh table (below); the count is always 1 |
| 0x48 | 0x3A0, 0x6710 | 0x2DE0, 0xD2E0 | vertex and index data: offset, size |
| 0x50 | 0, 0 | 0x1A74, 13 | ragdoll bodies of a character (joint limits such as +-60 degrees; not decoded) |
| 0x58 | 0x6AC0, 0 | 0x100D0, 0 | the tail: four zero bytes, or a character's physics objects to the end of the file (CHARACTERS.md) |
| 0x60 | 0, 0x62 | 0, 0x62 | |
| 0x68 | 0x104, 0x56 | 0x3AC, 0x336 | string table: the texture paths (their size), the bone names, the parts' names (upper case; a weapon's are its bones') |
| 0x70 | | | bounding box in the model in the bind pose: min, max of x, then of y, then of z |
| 0x88 | | | bounding sphere: centre, radius (not around the box's centre in the games' models) |
| 0x9C | 1/32767 | 1/32767 | position scale (0.002 in the Beretta and the third-person models) |
| 0xA0 | 0.5, 1/65536 | 0.5, 1/65536 | texture coordinate offset and scale (1.5 and 5/65536, -1 to 4, in `merc_prtoto01`) |

## Bones and skin matrices

A bone: first child, next sibling, parent (-1 for none), rotation (x, y, z, w), position, scale (3 floats
each) relative to the parent, its skin matrix (-1 for none), 1.0, its ragdoll body (u16, 0xFF for none), the
u16 offset of its name in the string table, 0, a hash (not the CRC-32 of the name). Parents come before
their children; bone 0 is the root. A bone's frame in the model is its parent's times its own (rotation as
the usual unit quaternion, then the position). The MP5's bones: `B_FRAME` at the origin, `b_Magazine` at
(0.218, 0.034, 0.034) and `b_Slide` (the cocking handle) at (0.349, 0.055, 0.143), both children of the
frame, no rotation.

The skin matrices (characters): 4x4 floats, row-major, for row vectors (Direct3D, the translation in the
last row). Bone i's is the inverse of its frame relative to the root in the bind pose, inverse(root^-1 *
frame i): on all 80 skinned models of both games to 1.5e-6. The soldier has 55 for 57 bones; the root
(`BIP01`) and `Bip01_FaceRoot` have none.

## Parts

A part is a run of submeshes with a name: its triangle count (all its submeshes', degenerate ones not
counted), its first submesh, that one's vertex offset, 0, its submesh count << 16 | 1, a bounding sphere
(centre in the frame its vertices are stored in, radius), the offset of its name, its LOD (0 and 1 on a
character's `_LOD0` and `_LOD1` meshes, else -1 in Instincts and 0 in Evolution; the only other difference
between the two games' MP5 models besides the version byte), 0.

The weapons have one part per bone, part i on bone i. Which bone a rigid part hangs on is in the part index
(the `uh60` helicopter's two parts hang on bones 1 and 2; placed by them, 8 props fit their box that do not
by the part number). A character has its mesh (one part, or LOD 0 and LOD 1) and attachments such as the
body armour and the multiplayer logo plates (CHARACTERS.md).

## Materials

0x30 bytes: the shader (a hash; its low half is the vertex tag of the submeshes that use it), a colour
(`FFFFFFFF`, `FF7F7F7F` on untextured ones), `FF000000`, the diffuse texture, -1, the bump texture (texture
numbers, -1 for none), 1.0, two hashes or -1, flags (0x21 on bump-mapped ones), 0. Characters carry spare
untextured materials (shader `D26B0114`) that no submesh uses.

| Shader (low half) | Vertex: skinned / rigid | |
|---|---|---|
| 53BF | 28 / 24 | bump-mapped: normal, tangent, binormal (the weapons, most of a character) |
| 4507 | 32 / 28 | as 53BF with a colour |
| EFA2 | 28 | as 53BF |
| 7CC6 | - / 28 | normal, colour, tangent, binormal (props) |
| 3E9A | 24 | normal, colour |
| 5033, 60C1 | - / 20 | normal, colour (props) |
| 0114, 5D91, 7DEF, 9402, 9118, A67E, D831 | 20 / 16 | normal only (D831: sunglasses, 9118: the logo plates) |
| 8DAD | 16 / 12 | no normal (Carver's shadow and untextured models) |

## Submeshes

Nine ints each, as many as the parts' submesh counts add up to (the table has no end mark; a scan for
`FFFF` can run into the vertex data): `FFFF` + material index, vertex offset and index offset (both from the
data start), stride << 16 | index count, the vertex tag << 16 | vertex count, eight palette bytes, zeros.
The palette holds bone numbers (FF unused); a submesh with a bone in its palette is skinned. Each
submesh's vertices start 32-byte aligned from the data start (CD between), its indices follow them
directly. Indices are 16-bit triangle strips; degenerate triangles join the walks. Seen from the front a
triangle's vertices go clockwise: for an even triangle of the strip (a, b, c), cross(b - a, c - a) points
away from its normals (Direct3D's default).

The data starts 16-byte aligned 4 to 16 bytes after the submesh table (in all 546 models), its size ends
16-byte aligned, and the tail follows 16 CD bytes later. A rebuilt weapon with its tail right after the
32-byte aligned data works in the game too.

## Vertices

Positions are int16 times the position scale, followed by an int16 1; texture coordinates int16 times the
uv scale plus the offset (v down the image, as in Direct3D). Directions are D3DCOLORs: bytes z, y, x around
128 ((b - 128) / 127), then 128; a colour is a D3DCOLOR (bytes b, g, r, a). A skinned vertex has 4 bytes
more after uv: two weights (bytes adding up to 255), then 4 times the palette slot of each (byte 12 goes
with byte 14, 13 with 15; 255, 0, slot, 0 for one bone). What follows depends only on the bytes left:

| Bytes left | Fields | Sizes: rigid / skinned |
|---|---|---|
| 0 | | 12 / 16 |
| 4 | normal | 16 (third-person weapons) / 20 |
| 8 | normal, colour | 20 / 24 |
| 12 | normal, tangent (+u), binormal (-v, up the image) | 24 (first-person weapons) / 28 (characters) |
| 16 | normal, colour, tangent, binormal | 28 / 32 (characters) |

Checked on the MP5's 664 frame triangles: the normals agree with the faces (0.97), the tangents with +u
(0.98) and the binormals with -v (0.97), each only in the z, y, x byte order. The colour of 32-byte
character vertices is a mask: nearly always exactly one of r, g, b, a is 255 (what it selects is open).

The weapons are rigid: each part's vertices are in its bone's frame (the MP5's magazine around its bone's
origin; placed by its bone the model's box is the header's to the float). The animations move the bones.
Units are metres, X is the muzzle, Z up; the third-person MP5 has the first-person one's size and
place, so one placement serves both.

## Skinned vertices

Proven on all 80 skinned models of both games (2026-10-30):

- Positions are stored in the root bone's frame in the bind pose: placed by the root, every skinned model's
  vertices fill the header's box to 2 mm (the soldier's boots end at -31246/32767 below the root at 0.9548,
  0.0012 above the floor, the box's minimum). At 1/32767 that is +-1 m around the pelvis.
- The palette names bones, not skin matrices, and byte 12 is the weight of slot byte 14: read so, vertices
  lie nearest their main bone (median 0.11 m in the soldier, 0.16 to 0.23 m read otherwise), and posed
  models bend cleanly; read otherwise they tear.
- In a pose a vertex is the sum over its bones of weight * frame(bone) * skin matrix(bone) * position; in
  the bind pose that is root * position.
- Software-rendered with their textures, in the bind pose and with elbows, knees, shoulders, head, jaw and
  fingers bent: a correct T-pose and clean bends for the soldier, `merc_prtoto01`, `merc_kit_04`, `chucker`,
  `sapper`, `freak_sapper_kit_01`, `krieger`, `crowemutant`, `scientist03` (Instincts), `pirate_kit_01`,
  `rebel_kit_02`, `feral_warrior_kit_02`, `ff_kit_01`, `barman`, `mp_uber` (Evolution).

## Rebuilding a character (xbg.rebuild_skinned)

New geometry on the template's skeleton: per part meshes in the model in the bind pose, each vertex with up
to two (bone, weight) pairs, each mesh split into submeshes of at most 8 bones (vertices shared across a
split are copied). The submesh table may grow (data and tail move along); written anew are the submesh
table, the parts' first submesh, count, triangles and sphere, the header's box, sphere, scale, data and tail;
the rest is kept byte for byte (materials to part index, the physics tail). A part can be kept as it is.
All 80 skinned models re-encoded from their own decoded geometry give back the same geometry in the bind
pose and in a bent pose (submeshes 0 to 4 fewer, files 3 to 9 % larger: shorter strips). Not tried in the
game yet.

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

## Counter displays (tools/weapon_import.py "counter", src/xbr/fci_counter.cpp)

A Halo rifle's display (the rounds in the magazine and a compass) is drawn by the renderer into a texture of its
own (2026-10-30). The importer gives the display's triangles their own material and texture:

- **Model.** `xbg.add_material` puts a copy of the weapon's material after the others, its diffuse and bump
  textures two new paths (the texture list grows by two entries, the paths go after the texture paths in the
  string table, the bones' and parts' name offsets move along; every block keeps its 16-byte alignment).
  `xbg.add_submesh` adds an empty submesh with it after the frame part's submeshes (the table grows, the data
  moves to the next 16-byte boundary at least 4 bytes after it, the later parts start one submesh later);
  `rebuild` fills it. The games load the new textures from `weaponpack` like the others (the mod menu's merge
  adds files an archive lacks).
- **Triangles.** The config's groups pick them (glTF materials, pieces as in `drop`, triangles `within` a box,
  texture coordinates inside `uv`). A `crop` group keeps its look: its texture coordinates' region of its
  material's maps (base colour plus emission, as the atlas) becomes the texture, `flip` turning it upright; a
  `rect` group's coordinates are spread over a rectangle of the texture on a plain background (Halo's separate
  digit and compass quads). Materials only the display uses stay out of the atlas, so the rest of the weapon
  and every other mod build byte for byte as before.
- **Texture.** A8R8G8B8 (the .xbt format 0x0C, swizzled), all levels to 1 x 1, alpha the gloss; `erase` boxes
  paint the old marks out at the source's resolution (what stands out bright from the box's median, filled from
  the texels around it). Its flat normal map is a 4 x 4 DXT1. Row 0 of level 0 carries the marker in the blue,
  green and red bytes of its first 18 texels (alpha 255, so an X8R8G8B8 read keeps it): `FCIC`, version 1,
  flags (1 compass, 2 digits), the tens', ones' and compass's boxes (4 x u16 texels each), the digits' fill and
  edge, the compass's edge and fill, the glow and its strength, the edge width (1/16 texel), the glow's reach
  (1/4 texel), a segment's thickness and gap (/255 of the digit's width), `CTR1`.

The renderer (d3d12.cpp, marked FCI) looks for the marker when it decodes a plain colour texture's level 0 for
upload (four bytes compared otherwise), keeps that level with row 0 replaced by row 1, and when it binds the
texture, once a frame, asks the game code's state for the frame it draws (src/fci_counter.c,
re/notes/WEAPONS.md): when the rounds or the needle (to a tenth of a degree) changed it draws the boxes anew
from the kept level (seven-segment digits and a ring with a pointer to the north, each a distance field with a
fill, a bright edge and a glow, Halo CE's assault rifle's colours by default), box-filters the levels below
and uploads them in the frame's command list, as a guest texture the title wrote to. Frame replay executes those
copies again with the frame, so a replayed picture shows its frame's digits. Nothing else changes for a
texture without the marker; nothing runs while no counter texture is drawn.

Checked in game (the user's options, frame replay at 60): the MA5B on the MP5 (both games) and on the M4
(Evolution), the Halo CE assault rifle on the M16 (Evolution) and, built onto the MP5 for the user's save, in
Instincts. The digits match the HUD's number in every capture (shots, reloads, a switch to the pistol and back),
the needle turns with the view and agrees with the HUD's compass strip, and in a dump of every picture shown
during a burst of fire (RECOMP_FCI_XBR_REPLAY_DUMP) the replayed pictures show their frames' digits. Not seen in
game: the Instincts M4 and M16 builds (no save with those weapons; the same configs as Evolution's).
