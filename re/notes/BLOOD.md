# Blood

Found 2026-10-30 from both games' level archives, `lua.dat`, `common.dat` and Instincts' XBE (addresses below
are Instincts' `default.xbe`; Evolution's has the same strings and tables at other addresses); recoloured
with tools/blood_recolor.py. Both games make blood the same way, from the same files.

## How a hit picks its blood

A bullet or melee hit goes to the engine's hit-effect code (sub_0046F430, called from three places), with
the hit surface's material and the kind of hit (a switch over 9). The material is an index into
`particles\materials.dat` (in every level archive and `farcryed`, byte for byte the same in both games):
`FTAM`, version 1, 50 entries of 0x70 bytes, read at level start by sub_0046F350 into 0x006B1518 (it also
names "HardCodedDecalAndParticles"). Per entry: +4 a particle effect (an index into a table of effect names
in the XBE, 0x00643C90, 24 names), +0xC a decal (into a table of texture names, 0x00643CFC, 12 names), more
indices and floats not decoded (likely sounds and sizes).

| Effect index | Name (`GFX_Particle_Bullet_Hit.<library>.<effect>`) |
|---|---|
| 0, 1 | `..._Blood_Medium_A`, `..._Blood_Small_A` |
| 2 to 23 | concrete, earth, extinguisher, gas bottle, glass, grass, knife sparks, knife flesh, knife flesh small, knife wood, metal, sand, stone, leaves, water, wood plank, wood trunk, pebble, water small, gas bottle, straw, mud |

Materials 3 and 30 to 35 have effect 0 and decal 6 (`GFX_Decal_Bullet_Hit_Flesh_A`; 35 has decal 7, metal):
the flesh materials. sub_0046F9B0 sends effect 0 or 1 to the blood table 0x00643C7C, `..._Blood_Big_A`,
`_Medium_A`, `_Small_A`, indexed by a size its caller gives; every other effect plays from the material
(sub_0046FB00). Melee on flesh puts `gfx_decal_bullet_hit_flesh_slash` (a second table, 0x00643D34: wood,
metal, flesh slash).

So the blood is one set for every character: no entity class, model, property or AI pack takes part, and
Jack, the enemies, the workers, Valerie and the animals bleed alike. A per-creature blood would need the
engine to look at what was hit there (a hook in the recompiled code), or a new material per creature in
`materials.dat` together with effect and decal tables that have more blood entries; neither exists.

## The pieces

| What | Where | Look |
|---|---|---|
| spray on a hit | particle effects `GFX_Particle_Bullet_Hit_Blood_{Big,Medium,Small}` (A, B, C and a sprite each) in every level's `levels\<level>\<level>_DepLoadParticles.xml` | `\Magma\Textures\Hud\damage_21.XBT`: 64 x 64 DXT3, one flat red (142, 25, 16) with the splatter in its alpha; tinted grey (0.83), so the colour is the texture's; plus a white additive spark (`gfx_sparks_a`, weaponpack, shared with every bullet hit) |
| wound mark | decal `textures_xbox\decal\gfx_decal_bullet_hit_flesh_a.xbt` (64 x 64 DXT5, 7 mips) | dark red splat on the hit character, one quad per hit, gone after 2 to 4 s (see Decals) |
| knife slash | `gfx_decal_bullet_hit_flesh_slash.xbt` (64 x 64 DXT5) | a dark cut on a red smear |
| knife spray | `..._Knife_Flesh_Splash_A`, `..._Small_Splash` are in the name table but in no level's library: nothing shows | |
| blood on the water | per entity: `<ParticlesSystem effectPlayer_BloodOnWater=...>` in the mission and the default in each character script (merc, freak, sapper, chucker, crowe, dragon, pig, valerie, worker, player) = `GFX_Characters.GFX_Character_Blood_Under_Water.GFX_Character_Blood_On_Water` | `textures_xbox\sprites\gfx_human_bullet_hit_a.xbt`, untinted |
| Jack under water | player.lua also plays `..._Blood_Under_Water` | `gfx_blood_pool.xbt` tinted (0.518, 0, 0) |
| pools | no pool under the dead; `gfx_blood_pool.xbt` is only Jack's underwater cloud and 01_Beach's placed `WRE_GFX_Blood_Meat_Pieces` | |
| gibs | none on deaths. The Trigen sapper's self-explosion (Instincts 10, 11, 13): `GFX_Explosions_Sapper.*` throws chunks (`Metal_Piece_A` geometry tinted 0.26, 0, 0), red splashes (tints on `gfx_water_splash_bullet`, `gfx_ripple_a`, `gfx_fire_lava_a`) and `gfx_blood_splash_a.xbt`, and leaves `gfx_decal_explosion_bloodsplat_df.xbt` (sapper_x.lua `texExplosionDecal`; the sappers and their spawn spots are its only users) | |
| scripted blood | Krieger's death (Instincts 13, Evolution 30: `BLF_GFX_Blood_Krieger_*`), Evolution 22 (`duneb_gfx.blood`), 26 (`4_1_3_.blood_spit`), 30 (`7_1_2.blood`, `7_3_5`, `7_3_6`): `damage_21` again | |
| set dressing | `decal_bloodsplat` (01_Beach bunker), `deadbodies_blood`, `misc_radiostation_bloody`, the multiplayer piranhas | their own textures |
| Jack's damage screen | the HUD's `magma\textures\hud\damage1.xbt` in `common.dat` (a white wedge the HUD tints red) | another file: `damage_21` is only in the level archives and `farcryed` |

Every blood texture above has one size in all levels of a game and the same in both; the particle library
is in each level archive. Names: the archives store `levels\<level>\<level>_DepLoad.xml` (the dependency
list), `levels\<level>\<level>_DepLoadParticles.xml` (the particle library, `<Particles Name="lib.effect">`
then effects of the same library by their name alone; an effect nests: its emitter `<Params>`, the `<Params>`
of the particle each of its particles spawns, then `<Childs>` with more effects) and `particles\materials.dat`; dat2.py
does not find these names yet (they are built from the level name in the code).

## Decals

Found 2026-10-30 from the XBE (sub_0046F430 and below) and test runs in Instincts' 02_Native and Evolution's
21_DUNEA with test values. A particle effect cannot leave a decal: the library's emitters have no such
parameter (the attributes are the 48 of every `<Params>`, none names a decal), and the sapper's splat on the
ground comes from its explosion (`ExplosionParams` with `texExplosionDecal` in sapper_x.lua, the explosion
code puts it under the blast like a grenade's scorch).

A bullet or knife hit leaves the material's decal (sub_0046FEF0, sub_0046FF90): texture = the decal table
entry at the material's +0xC, size = +0x10 plus a random part (rand - 0.5) * 2 * +0x60 (metres; flesh
0.025 +- 0.125, so 0 to 15 cm), a random turn of 0 to 360 degrees, and a last value of 2.0 for flesh hits and
15.0 for the others (likely the lifetime in seconds: flesh marks vanished 2 to 4 s after the hit in every
run). sub_0046FFD0 hands it to the decal manager (sub_0045AA60) with the hit entity: on a character the quad
belongs to that entity (moved into its space), not to the wall behind or the floor. The byte 0x006B4AF1
(likely the gore setting) skips flesh decals and the blood sprays when set.

Floor splats from particles do not work either: a flat emitter (Flags 1, the water splashes' flag) that
falls from the hit vanished within 1 to 2 s whatever its Bounciess (0, 0.05, 0.3) and LifeTime (12, 30),
while the same emitter without gravity lived its 30 s: falling particles die where they meet the ground.
Splats on walls and floors need the engine's help: src/fci_blood.c (next section).

## Splats on walls and floors (src/fci_blood.c)

Found and built 2026-10-31. A prehook on the hit decal's placement (Instincts sub_0046FEF0, Evolution
sub_003347F3: esi = the material's entry; entity, position, normal, part, life; cdecl) acts when the engine
puts the flesh decal on a hit character (an entity, the material's decal 6, the gore byte clear): it casts
two rays with the engine's own ray test, against static entities and terrain only (types 0x101, flags 0x100
as the scripts' System:RayWorldIntersection, so the hit body and other characters are not in the way), from
the hit point 3 m down and 3 m on along the shot (the hit normal faces the shooter: the ray goes against
it), and where they meet the world it calls the engine's decal routine with no entity, as for a bullet hole:
the flesh decal's texture (with the blood mods the game's splat in the mod's colour, `halo-blood-red` the
same splat red; without a blood mod the game's small red wound mark), a random turn, the size by the hit
(big 1.0 m, medium 0.75, small 0.55, each +-20 %, times gfx-blood-splats-size) and the life value 30
(bullet holes 15, the mark on a body 2). The splats lay flat on the ground and stayed at least 30 s in the
runs.

| | Instincts | Evolution |
|---|---|---|
| hook | 0046FEF0 (tools/compile.py) | 003347F3 (its profile, the hook named 0046FEF0) |
| decal routine | 0046FFD0: ecx = position, eax = normal, edx = texture; size, entity, part, life | 003348CD: the texture in edi |
| ray test | 00376000 (world, origin, direction, types, flags, max hits, skip, skip), ebx = hits, ret 0x30 | 00284467: ebx = world, the hits after the flags |
| physical world | [006B38F8] (the bullet's own ray, 000EA558) | [0056B508] |
| decal textures, gore byte | 006B14E4, 006B4AF1 | 00568DA4, 0056C6F1 |
| blood size | the call's return address: 0046F83D big, 0046F8B5 medium, 0046F925 small | one call (00334439) for kinds 5 to 7: the dispatcher's kind 0x40 above the return address |

A ray hit is FC1's ray_hit (0x34 bytes: dist, collider, part, part id, surface, point +0x14, normal +0x20,
terrain, next); the first is the solid hit. The hook saves and restores the guest registers, the XMM
registers and the x87 stack around its calls. Limits: one floor and one wall splat a hit, none within 0.3 m
of the last 32, at most 10 a second; past that the engine's decal manager keeps its own pool (its size not
decoded; with 16 splats down at once nothing was lost). fci.ini `gfx-blood-splats = 0` switches it off,
`gfx-blood-splats-size` scales it; RECOMP_FCI_BLOOD_SPLATS_LOG=1 prints each hit and splat.

Checked in the game (test installs, the user's display options, the Elite blood mods): Instincts' 02_Native
from the user's save, Elites hit on the jungle path at 10 to 15 m: blue-violet splats on the path's edge and
on the road beside a dead Elite, none with the switch off (fci-modsrc out/halo-blood/
ingame-splats-before-after.png); the log puts them 0.2 to 1.4 m below the hits, normals up. Evolution's
opening ride: splats on the road at the gate (log), drawn as world decals; no frame caught them in view.
No splat on a wall yet: the fights in these two places had no wall within 3 m behind the target (the log
says so per hit), and on a low hit the shot's ray meets the ground behind.

## The mods (tools/blood_recolor.py)

A colour is a linear map that takes the blood's red to a Halo colour and leaves greys grey (out = m + (r - m)
T, m the mean of green and blue). Being linear it is applied to the two colour endpoints of every DXT block,
mip level by mip level: shapes, alpha and block indices stay the game's; an endpoint pair the map turns round
is swapped back with its indices so the block keeps its mode. Particle tints (StartColor, EndColor) of named
libraries go through the same map where they are reddish; the rest of the library stays byte for byte.

Sprays: every active emitter of the three blood libraries that draws `damage_21` gets Size and SizeSpeed
x 2.5, Count x 2, Speed x 1.3, LifeTime x 1.4 (12 emitters a level, config "spray"). With automatic fire up to
about 500 spray particles were on screen in one frame (Instincts' plasma rifle at 15 m), drawn in a dozen
draws, without a limit showing. Stains: the flesh materials 3 and 30 to 34 leave their mark at
0.4 +- 0.1 m (config "stains"; 35 also bleeds but leaves the metal decal and stays), with the sapper's splat
texture (`gfx_decal_explosion_bloodsplat_df`, Instincts' 10_Dead_Marshes, recoloured) in place of
`gfx_decal_bullet_hit_flesh_a`. Every blood mod writes these per campaign level (`levels/[0-9]*`): the
recoloured textures, the particle library, `particles/materials.dat`.

The mods (fci-modsrc `halo/blood/<game>.json`, folders `mods/<game>/halo-blood-*`); one set of alternatives
(the menu keeps one on) and, in Instincts, the sapper mod beside it:

| Game | Mod | Colour (from red 142, 25, 16) |
|---|---|---|
| both | `halo-blood-elite` | Elite blue-violet (92, 78, 240) |
| both | `halo-blood-grunt`, `halo-blood-jackal` | Grunt cyan (64, 196, 240), Jackal purple (160, 56, 224) |
| Instincts | `halo-blood-hunter`, `halo-blood-flood` | Hunter orange (240, 128, 28), Flood pale yellow-green (186, 204, 104) |
| both | `halo-blood-red` | none: the game's red with the bigger sprays and stains |
| Instincts | `halo-blood-sappers-flood` (own set) | `gfx_blood_splash_a`, `gfx_decal_explosion_bloodsplat_df` in 10, 11, 13, Flood |

In Instincts every coloured blood mod also turns the sapper explosion's 26 reddish tints (levels 10, 11,
13) Flood yellow-green (config "tints"), since all of them write those levels' particle library.

What else bleeds the chosen colour: everyone (Jack's allies and the named people, workers and scientists,
Valerie / the femme fatale, Krieger, the lizards, Jack on the water) and the scripted blood above.
Left red: Jack's damage screen, his underwater cloud (`gfx_blood_pool` under a red tint: a change would need
the library's tint and the pool texture, which 01_Beach's meat pieces share), the set dressing.

## Checked

- Offline: swatches of every recoloured texture and tint per colour (`--check`).
- Evolution, 21_DUNEA's opening ride (test install, the user's mod set plus `halo-blood-elite`): when the
  mounted gun hits the pirates (Elites) at the gate, the frame's dumped textures include the spray texture
  and the wound decal identical to the mod's files (mean difference 1.0 and 0.7 of 255), drawn as particles
  (alpha blend) and a decal quad; the game's red ones never appear. The spray is a few pixels at that range.
- Instincts, 02_Native from the user's save (test install, a closed-loop test driver that turns onto the
  Elites it sees and fires): with the first version the frames bind the recoloured spray and wound mark,
  never the red ones (so the colour reaches the game; the spray is a few pixels at 15 m). With the bigger
  sprays and stains a hit at the same range throws a blue-violet burst over the whole torso, still showing
  2 s later; spray and stain textures again identical to the mod's files.
- Evolution, the bigger version: the mods are active and 21_DUNEA runs (three ride runs), but no hit fell on
  a captured frame; its edits are Instincts' (the same three libraries and 12 emitters a level, the same
  material list).
- Offline for every built mod: each particle library parses and differs from the game's only in the blood
  emitters' Size, SizeSpeed, Count, Speed, LifeTime and the sapper tints; materials.dat only at +0x10 and
  +0x60 of materials 3, 30 to 34.

## Open

- In the game: Evolution's bigger sprays (no hit on a frame), the sapper explosion (levels 10, 11, 13).
- Splats (fci_blood.c): a wall splat and an Evolution splat in view not seen in the game yet; knife hits
  (sub_0046FF90, the slash decal) leave none; without a blood mod the splat is the small wound mark; the
  decal manager's pool size and what the life value (2, 15, 30) counts are not decoded.
- The size argument of the blood table (damage, weapon or distance) and the rest of a material entry.
- Per-creature blood (an engine hook on sub_0046F9B0 that picks the effect by what was hit, and new effect
  entries in the libraries); Jack's underwater cloud and the scripted human blood would then stay red.
