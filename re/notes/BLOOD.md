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
| wound mark | decal `textures_xbox\decal\gfx_decal_bullet_hit_flesh_a.xbt` (64 x 64 DXT5, 7 mips) | dark red splat; in the game a quad on the world near the hit (the decal vertex shader), one per hit, staying |
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
then effects of the same library by their name alone, not nested) and `particles\materials.dat`; dat2.py
does not find these names yet (they are built from the level name in the code).

## Recolouring (tools/blood_recolor.py)

A colour is a linear map that takes the blood's red to a Halo colour and leaves greys grey (out = m + (r - m)
T, m the mean of green and blue). Being linear it is applied to the two colour endpoints of every DXT block,
mip level by mip level: shapes, alpha and block indices stay the game's; an endpoint pair the map turns round
is swapped back with its indices so the block keeps its mode. Particle tints (StartColor, EndColor) of named
libraries go through the same map where they are reddish; the rest of the library stays byte for byte.

The mods (fci-modsrc `halo/blood/<game>.json`, folders `mods/<game>/halo-blood-*`), for the campaign levels
(`levels/[0-9]*`; the enemies are there):

| Game | Mod | Files | Colour (from red 142, 25, 16) |
|---|---|---|---|
| both | `halo-blood-elite` | damage_21, flesh_a, flesh_slash, human_bullet_hit_a in every campaign level | Elite blue-violet (92, 78, 240) |
| both | `halo-blood-grunt`, `halo-blood-jackal` | the same files: alternatives | Grunt cyan (64, 196, 240), Jackal purple (160, 56, 224) |
| Instincts | `halo-blood-hunter`, `halo-blood-flood` | the same files: alternatives | Hunter orange (240, 128, 28), Flood pale yellow-green (186, 204, 104) |
| Instincts | `halo-blood-sappers-flood` | 10, 11, 13: the sapper library's 26 tints, `gfx_blood_splash_a`, `gfx_decal_explosion_bloodsplat_df` | Flood |

What else bleeds the chosen colour: everyone (Jack's allies and the named people, workers and scientists,
Valerie / the femme fatale, Krieger, the lizards, Jack on the water) and the scripted blood above.
Left red: Jack's damage screen, his underwater cloud (`gfx_blood_pool` under a red tint: a change would need
the library's tint and the pool texture, which 01_Beach's meat pieces share), the set dressing.

## Checked

- Offline: swatches of every recoloured texture and tint per colour (`--check`); the particle libraries
  parse and differ from the game's only in the sapper library's StartColor and EndColor (13 lines per level).
- Evolution, 21_DUNEA's opening ride (test install, the user's mod set plus `halo-blood-elite`): when the
  mounted gun hits the pirates (Elites) at the gate, the frame's dumped textures include the spray texture
  and the wound decal identical to the mod's files (mean difference 1.0 and 0.7 of 255), drawn as particles
  (alpha blend) and a decal quad; the game's red ones never appear. The spray is a few pixels at that range.
- Instincts: the mods merge (46 switched on, the blood mods active) and the game goes into its first level.

## Open

- Close-up in the game: the ride's hits are 20 m and more away; Instincts not hit in the game yet; the sapper
  explosion (levels 10, 11, 13) not seen in the game.
- The size argument of the blood table (damage, weapon or distance) and the rest of a material entry.
- Per-creature blood (an engine hook on sub_0046F9B0 that picks the effect by what was hit, and new effect
  entries in the libraries); Jack's underwater cloud and the scripted human blood would then stay red.
