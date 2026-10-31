# Weapon ranges

Data: `lua.dat` and `lua.fat` on both discs. Found 2026-10-25 from the compiled weapon scripts, read with
tools/luadat.py; changed with tools/weapon_range.py.

## The archives

`lua.fat` indexes `lua.dat` (and likewise `common`, `weaponpack`, the sound banks): `DAT2`, a count, then
per file its offset, size and a hash of its name (12 bytes; the names are not stored). All 404 files of
Instincts' `lua.dat` and 448 of Evolution's are compiled Lua scripts.

## The scripts

A Lua 5.0-like chunk: the header `1B 'Lua' 41`, then little endian, 4-byte ints, size_t and instructions,
and 4-byte float numbers (the test number is 314159265 as a float). Each function: source (`=(none)`),
five ints, line info (empty), locals (empty), typed constants (3 a string, 0 nil, else a float), nested
functions, code. The reader ends exactly at the end of every script in both games.

An instruction is 32 bits: op = w & 0x3F, A = w >> 24, Bx = (w >> 6) & 0x3FFFF, sBx = Bx - 0x1FFFF.

| Op | | |
|---|---|---|
| 1 | LOADK | R(A) = K(Bx) |
| 2 | LOADINT | R(A) = sBx: integers are not constants |
| 8 | SETTABLE | R((w >> 15) & 0x1FF)[RK((w >> 6) & 0x1FF)] = R(A); RK from 250 up is constant RK - 250 |

So `damage = 30` in a table compiles to a LOADINT and a SETTABLE whose key is the constant `damage`.

## FireParams ranges

Each weapon script (its first string constant is the weapon) builds a `FireParams` table with
`distance` and `distance_max` in metres, and the same for multiplayer. Played: a shot past
`distance_max` does not hit, which is why the guns seem to stop short. Read in both games, identical
in both (Evolution adds the blowgun):

| Weapon | distance | distance_max | multiplayer |
|---|---|---|---|
| Berretta, BerrettaNoSup (Beretta M9) | 25 | 30 | 20 / 35 |
| Glock | 20 | 30 | 15 / 30 |
| DE (Desert Eagle) | 30 | 40 | 30 / 45 |
| MP5, P90 | 30 | 40 | 20 / 35 |
| M16 | 30 | 45 | 35 / 45 |
| M4 | 35 | 70 | 40 / 55 |
| FNM249 | 35 | 45 | 30 / 40 |
| Browning | 40 | 60 | 35 / 60 (Evolution 35 / 70) |
| HKSL8, BarrettM82A1 | 150 | 200 | 200 / 250 |
| M1S90 (shotgun) | 10 | 20 | 10 / 20 (Evolution 15 / 25) |
| M202 | 100 | 110 | 100 / 110 |
| BlowGun (Evolution) | 15 | 20 | 10 / 15 |
| DragonDart | 30 | 30 | |
| Seringe_Gun | 1.6 | 3.2 (constants) | |

The M16 script has a second table of zeros (its grenade launcher); melee weapons and grenades are 0.

## AI ranges

The character scripts set `sightrange` (mostly 150 to 220 m for soldiers), `attackrange` (70 m in 17
of 22; read in Instincts) and `commrange`. Enemies fire from their weapon's script too, but only within `attackrange`.
With longer weapon ranges the player can hit enemies from farther than they return fire.

## Longer ranges (tools/weapon_range.py)

The tool rewrites each range's LOADINT in place (`RANGES`: pistols 50 / 150, the MP5 and P90 100 / 250,
rifles and the M249 250 / 600, the Browning 300 / 800, the SL8 400 / 1000, the Barrett 600 / 1500, the
shotgun 25 / 60). `lua.dat` keeps its size, so `lua.fat` stays valid, and no other byte changes (checked
against the original in both games: 26 instructions, nothing else). The original stays as
`lua.dat.orig`. Multiplayer ranges, `attackrange` and the rest are left.

Played by hand: shots land well past the old limits, and enemies hold fire until their attack range.

Open: where the engine reads `distance` and `distance_max`, and how the damage falls between them
(full damage up to `distance` is read from the name).

# Weapon scripts as mod files (tools/lua_patch.py)

Found 2026-10-30 from both games' `lua.dat`, the XBE and the levels' archives.

## Names

A script's name in `lua.dat` is its path with `_compiled` after `.lua`:
`\scripts\default\entities\weapons\p90.lua_compiled`, `\scripts\default\gamerules.lua_compiled`. With that
rule the XBE's paths and the scripts' own strings name 323 of Instincts' 404 scripts and 341 of Evolution's
448, among them every weapon script (`lua_patch.py list`). A mod replaces one as
`mods\<mod>\lua\scripts\default\entities\weapons\p90.lua_compiled`.

## Instructions

Lua 4.1 (work) as the XBE calls it: op = w & 0x3F, C = (w >> 6) & 0x3FF (10 bits), B = (w >> 16) & 0xFF,
A = w >> 24; Bx = (w >> 6) & 0x3FFFF. An RK operand (C) from 250 up is constant C - 250, so up to 773
(checked: all 427 and 1,483 table accesses with bit 15 set name a string constant). Opcodes in order:

    MOVE LOADK LOADINT LOADNIL LOADUPVAL GETGLOBAL GETTABLE SETGLOBAL SETTABLE NEWTABLE SELF ADD SUB MUL DIV
    POW UNM NOT CONCAT JMP CJMP TESTEQ TESTNE TESTLT TESTLE TESTGT TESTGE TESTT TESTF NILJMP CALL RETURN
    FORPREP FORLOOP TFORPREP TFORLOOP SETLIST SETLIST0 CLOSURE

SETTABLE: R(B)[RK(C)] = R(A); GETTABLE: R(A) = R(B)[RK(C)]; LOADNIL: R(A) .. R(B) = nil; NEWTABLE A Bx (Bx
the size); SETLIST A Bx: R(A)[Bx - Bx % 32 + i] = R(A + i) for i = 1 .. Bx % 32 + 1. Number constants are
tag 2 (4-byte float), strings tag 3. (tools/luadat.py's note on SETTABLE's table register and its 9-bit key
read are off; they do not matter for the range fields it reads.) Every weapon script's main function is
straight code without jumps: a constructor into R0, SETGLOBAL, `CreateBasicWeapon(...)`, more fields.

## Effect fields (FireParams[n], read by BasicWeapon's fire code)

| Field | | Use |
|---|---|---|
| `BulletTrail` | colorA, colorB (r, g, b), speed, alphaMul, length, head_length, width, texture | if set (and not `bUseSFX`): `Particle:CreateParticleLightLine(..., dir, dist, BulletTrail)` |
| `MuzzleParticle` | effect, bulletCases (particle effect names) | `AttachMuzzleEffect(hand, ..., effect)`; `SpawnEffectFromWeaponBone(..., bulletCases)` only if bulletCases is set |
| `MuzzleLight` | color, diffuseMul, radius | if set: `SpawnMuzzleLight(..., color, diffuseMul, radius)` |

Not every weapon has all: the suppressed Beretta has neither tracer nor light, BerrettaNoSup no light, the
Mortar (MK19) no tracer. Tracer textures (`objects_xbox\weapons\bullet_tracer\bullet_tracer03.xbt`, an orange
streak, ten guns; `bullet_tracer04`, the scoped rifles and the blowgun) are in `weaponpack`.

Effect names are `<library>.<effect>`; the particle library is one XML file (`<ParticleLibrary>`, 433 effects
in Instincts' 01_Beach) in each level's archive, every level holding all weapons' effects. A muzzle flash is a
particle whose `Geometry` is a model in `weaponpack` (`animations\weapons\first\mk19\mk19_muzzle_flash.xbg`) with
its own textures (`mk19_muzzle_flash_a.xbt`, `_b.xbt`), tinted by the particle's StartColor and EndColor. Flash
models shared: Glock and Desert Eagle, P90 and MP5. A level's `<level>_DepLoad.xml` lists per weapon the files
and effects it needs (models, `.xba`, effects as type 10, the tracer texture as type 1).

## The tool

`lua_patch.py` reads a script into its functions (written back byte for byte: all 852 scripts of both
games), follows the main function's table building and changes named fields: a value's load instruction
is rewritten in place (LOADINT, LOADK with a constant added when missing, LOADNIL for nil), and a field the
script does not set is added by code right after its table's NEWTABLE (registers above it are free there; the
stack size grows when needed). Paths go from the weapon's table (`FireParams[*].MuzzleLight.color`). `patch`
reads every written file back and stops when anything else differs; `diff` shows what a mod's scripts change.
The Halo weapon mods use it (fci-modsrc `halo/weapons`, `"lua"` in their configs).

## Effect hooks (`"effect_hooks"`, BasicWeapon)

Found 2026-10-31. The game has no field for an effect where a bullet hits (impacts come from
`Game:ExecuteMaterialFX` by the surface's material, the same for every weapon) and only the attached
`MuzzleParticle` at the muzzle. `basicweapon.lua_compiled` binds each handler twice, Server's then Client's
(`BasicWeapon.Server.OnFire`, `BasicWeapon.Client.OnFire`, the same order in both games); the hooks go into
Client's:

| Hook | Where | Registers there | Call |
|---|---|---|---|
| `FireParams[n].HitParticle` | `Client.OnHit`, before its one RETURN (every path ends there) | R1 the hit (`pos`, `normal`), R3 `FireParams[n]` | `Particle:SpawnEffect(hit.pos, hit.normal, effect, scale)` |
| `FireParams[n].MuzzleGlow` | `Client.OnFire`, right before it reads `BulletTrail` (after the muzzle flash and light) | R1 the shot (`dir`), R5 the fire mode's params, R8 the muzzle position | `Particle:SpawnEffect(muzzle, shot.dir, effect, scale)`, only with a muzzle position |

Both are `{effect = "<group>.Lib.Effect", scale = 1}`; a fire mode without them runs as before (the hook tests
the field first). Checked in both games: the Halo plasma mods' bursts appear where the shots hit (Instincts
02_Native from the user save, Evolution 21_DUNEA), and a glow from `MuzzleGlow` shows at the muzzle, where the
same effect as `MuzzleParticle` (attached to the weapon's muzzle bone) did not show in first person; an AI
firing the weapon gets the glow too. The code goes in with every old jump moved past it (a jump to the RETURN lands on the hook),
in registers free at that point (OnHit R4 up, OnFire R13 up, under the functions' stack sizes 17 and 31); the
functions have no line info. `SpawnEffect`'s fifth argument (a colour) only scales the lighting of lit
particles, so an additive effect cannot be tinted by it: a coloured effect is its own entry in the level's
library (README.md, Mods: `particles-add`). Effect names are looked up in the level's library whatever the
group (`GFX_Muzzleflash.Halo_FX.PlasmaPistol_Impact` finds `Halo_FX.PlasmaPistol_Impact`); only without a
level library (the menus) does a group load `Particles\<group>.xml`. The Mortar's shell
(`mortarshell.lua_compiled`, `ParticlesSystem.effectExplosionFire` on an object, `effectExplosionSmoke` on
the ground, `effectExplosionWater`, `effectExplosionFly` every 0.03 s in flight) takes other effect names as
ordinary fields. Every mod with the hooks ships the same BasicWeapon (from the same `lua.dat`), so they do not
conflict (src/fci_mods.c treats two files of the same bytes as no conflict).

# The magazine count and the heading (src/fci_counter.c)

Found 2026-10-30 from both games' HUD code (the `CryInGame_Hud` page's element names in `.rdata` and their
references) and checked in game against the HUD. The Halo rifles' displays (MODELS.md "Counter displays") show
both.

## The rounds in the magazine

The HUD's update (Instincts 001AB430, Evolution 00137981, once a frame in play) sets each of its counters
through a set-value function by kind (Instincts 001A9850, Evolution 00135D07: thiscall, HUD; the player, the
kind, the value, the maximum, a flag; a jump table by kind). Kind 4 is `t_counter1` of `ai_bullet`, the number
beside the bullet icon: Instincts 001A9480 (esi = HUD, [esp+4] = the number, ebx = its text; ret 4), Evolution
0013598A (ebx = HUD, [esp+4] = the number, [esp+8] the text; ret 8). Both compare the number with the shown
one (HUD +0x3A4, Evolution +0x43C) and only then change the text, so a prehook sees the number every frame.
Kind 6 is the magazines beside it (`ai_mag`), kind 5 the second gun's rounds when akimbo.

The number: the player's ammunition state (player +0x36C) at +0x18 + 4 * the fire mode (player +0x18C),
capped at the clip's size (the fire mode's +0x24 in the weapon's table); 0 for a weapon without rounds.
The script function `GetCurrentAmmoInClip` (000C5B00) reads the same state: +0x10 for its argument 1, +0x18
for 2 (kind 5, the akimbo count, shows +0x10). Checked by captures: the hook's number is the HUD's in every
frame, through shots, reloads and (Instincts) a switch to the pistol and back (Instincts 02_Native from the
user's save; Evolution 21_DUNEA with the M4).

## The heading

The HUD's compass strip (`ai_compass`, an animation of 160 frames for 360 degrees) is set by Instincts
001AA440 / Evolution 00136799 (eax = HUD, [esp+4] = the player's yaw + 90): it adds the HUD's compass offset
(Instincts +0x2A4, Evolution +0x328; 0 from the constructor, `Game.SetCompassOffset(degrees)` sets it,
000B8AAA / 000907E8), wraps to 0..360 and shows frame value * 4/9; value 0 is north. With the yaw falling to
the right (INPUT-CAMERA.md), the strip's middle is the bearing -(yaw + 90 + offset). Instincts' 02_Native sets
an offset of -90 (read from the HUD in play), so there the bearing is -yaw: at the user's save's start (yaw
-69.1) E stands just right of the middle, 30 and 60 degrees to the right put it left of it, 60 to the left of
the start brings N just left of the middle. A needle that left the offset (and the 90) out was off in both games
(02_Native by 90 degrees); with them it agrees with the strip in 02_Native and in Evolution's 21_DUNEA.

fci_counter.c takes the yaw from Player_ProcessInput's prehook (fci_aim.c: the block's angles minus this
frame's turnYaw, the yaw the camera of this frame gets) and the offset from a prehook on the strip's function.

## Frames

The renderer runs up to a frame behind the game code (xbr/gpu/render_thread.cpp: the title records a frame
while the one before draws). Read when the renderer draws, the number was a frame early (a capture showed 28
on the gun beside the HUD's 29). Each value is now kept with the title's count of presents at the time
(xbr/fci_counter.cpp `NotePresent`, in the threaded backend's Present), and the renderer reads the state of the
present count it draws: the gun and the HUD change in the same picture.

# Damage: weapon strength and enemy damage (src/fci_damage.c)

Found 2026-10-31 from both games' `lua.dat` (the single-player GameRules script, BasicWeapon, BasicPlayer) and
XBEs (the hit table builders by their key strings), checked in game in Instincts' 02_Native.

## Where the game applies it

The scripts apply all damage to characters. `GameRules:OnDamage(hit)` (the single-player GameRules, the script
whose first constant is `GameRules` and which builds `player_to_ai_damage`) takes `hit.damage`, multiplies it by
a table chosen by who hits whom and by the body part (`target_material_id` 30 head, 34 heart, 33 body, 32 arm,
31 leg; an explosion takes the sixth entry times `target:IsAffectedByExplosion()`), and calls
`GameRules:ApplyDamage(hit, target, damage, piercing)`, which takes armour off first (2/3 of the damage while
there is armour) and the rest off `target.cnt.health`. Instincts' tables (the same at every difficulty):

| Table | Head, heart, body, arm, leg, explosion | Used when |
|---|---|---|
| `player_to_ai_damage` | 9, 1, 1, 1, 1, 2 | an AI target, the shooter not an AI |
| `player_to_chucker_damage` | 1, 1, 1, 0.1, 1, 0.25 | a Chucker |
| `player_to_crowe_damage` | 1 each | Crowe (`Properties.bIsCrowe`) |
| `ai_to_ai_damage` | 3, 1, 1, 1, 1, 1 | AI on AI |
| `ai_to_player_damage` | 0.5 each, explosion 0.33 | any hit on Jack |

Evolution's script (the same name in its `lua.dat`) has `player_to_ai_damage` 9, 1, 1, 1, 1, 1,
`ai_to_ai_damage` and `ai_to_player_damage` 1 each, adds `player_to_boss_damage` (2, 1, 1, 1, 1, 0.25),
`ai_to_player_in_railshooter_damage` (0.15 each, the scripted rides) and multipliers by difficulty
(`difficulty_level_damage_multipliers` 0.8, 1, 1.2, 1.4 and a second table). The hooks below sit before all of it.

The shooter's `Properties.fWeaponDamageMultiplier` scales an AI's gunfire; `bFullDamageOnMeleeHit` makes an AI's
melee ignore the table. `hit.damage` comes from the engine:

- Bullets: the weapon's hit function (Instincts 000EBEE0, Evolution 000B648F; the hit struct its first argument:
  +0 position, +0xC normal, +0x18 direction, +0x24 damage, +0x28 target entity, +0x2C part, +0x34 shooter
  entity, +0x38 weapon, +0x40 material) fills the weapon's hit table, runs the weapon's `Server:OnHit` and
  `Client:OnHit` (000E89D0 / 000B3F84; the client one picks the blood's size by `hit.damage`: over 30 big, over
  15 medium) and then the target's OnDamage (entity vtable +0x128), which calls the script's. The damage is the
  fire mode's `damage` less the fall-off between `distance` and `distance_max` and less what the surfaces before
  took (000EBA70; Jack's own shots within 4 m count double in single player while the game object's +0x60,
  likely the difficulty, is at most 1).
- Explosions: the explosion code (Instincts 000B617F, Evolution 0008E48F) makes a table per entity in reach with
  `explosion = 1`, the shooter and `damage` = the explosion's damage times its fall-off, set through the script
  object's SetValue(key, float) (vtable +0x34: Instincts 002985A0, call at 000B6728; Evolution 001E7AEE, call at
  0008EABC), then calls the entity's OnDamage. Grenades, rockets and other projectiles all end here.
- Melee: the melee attack (Instincts 0007A1B0, Evolution 0005D370; ecx = the attacker's player object) finds the
  bodies hit and calls the BasicPlayer `MeleeAttack(hits)` script, which sets `hit.melee = 1`, `hit.damage =
  self.cnt.melee_damage` (the player object's +0x1A4, Evolution +0x1B0; set from the weapon before) and calls
  `target:Damage(hit)` (the script entity's Damage, 00211760: the entity's OnDamage).

Jack is the entity of the game's first player slot (Instincts [006B3984]+0x28, Evolution [0056B594]+0x2C; its
entity id at +0x30, 1000000 in play; an entity's id is at +0xA4). A character's container (entity +0x23C) is its
player object, pointing back at the entity at +4, with `cnt.health` at +0x160 (Evolution +0x178). Jack's player
class and the AI ones differ (vtables 005FC320, 0060D4D0 and others in Instincts) but share their base's
QueryContainerInterface (vtable +0x10); vehicles have another.

## The hooks (src/fci_damage.c)

The mod menu's settings (fci_mods.c, `mods\settings.ini`: `weapon-strength`, `enemy-damage`, 25 to 200 %) are
read at every hit, so a change counts from the next shot:

- A gate on the bullet hit finds the factor: the weapon strength when Jack hits a character, the enemy damage
  when another hits Jack. A gate on its OnHit call runs the OnHit scripts first and then sets the table's
  `damage` to the scaled value (SetValue through the table's vtable, the game's own "damage" key, Instincts
  005FC1AC, Evolution 004B034C), so the target's OnDamage gets it and the blood stays the size it was.
- A prehook on SetValue(key, float) scales the value when the call comes from the explosion code (its return
  address), the shooter and target read from that frame (Instincts [esp+0x3C] and ebp, Evolution [ebp-0x40] and
  ebx).
- A gate on the melee attack scales the attacker's melee_damage for the call and puts it back: Jack's by the
  weapon strength, anyone else's by the enemy damage (that also counts an AI's melee on another AI, rare).

At 100 % nothing is changed. `RECOMP_FCI_DAMAGE_LOG=1` prints each bullet hit by or on Jack with the target's
health before and after, each scaled explosion and melee.

## Checked

Instincts' 02_Native from the user's save (test install, the user's mod set: Halo weapons, Elites and blood; the
user's display options with frame replay; the keyboard mode left out, see below), the log on, the menu moved
with the pad (both sticks, d-pad steps, B) while the game ran, and a test aid (RECOMP_FCI_DAMAGE_TEST_AIM=1)
that turns Jack toward whoever last shot him:

| Weapon strength | Jack's MA5B on an Elite's body (damage 8 or 9) | body hits for 50 health | for 80 |
|---|---|---|---|
| 100 % | 8 off its health (50 -> 42 -> 34) | 7 body hits | 10 |
| 50 % (moved to live) | 4.5 off (50 -> 45.5 -> 41 -> 36.5) | 12 | 18 |
| 200 % (moved to live) | 16 or 18 off (50 -> 34 -> 18 -> 2 -> 0; 80 -> 62 -> 44 -> 26) | 4 | 5 |

A head shot (the table's 9) took a 50-health Elite in one hit at 100 %. Enemy damage: an Elite's 9 on Jack took
1.5 off his health while he had armour and 4.5 after it at 100 %, 0.375 at 25 % and 0.75 at 50 % (with armour).
The hit counts come from the measured damage; at 200 % the kills were seen too: a 50-health Elite in 3 or 4 hits
(damage 9 or 8), an 80-health one in 4 or 5. Jack's melee_damage (15) was 30 during his melee attacks at 200 %
and 7.5 at 50 % (none of them reached an enemy in these runs). The settings file follows each step (`[FCI]
settings:` in the log) and is read at the next start. The menu draws over the game with frame replay on.

The keyboard (RECOMP_KEYBOARD=1, at the title): F1 opened the menu, three Left arrows took the weapon strength to
85 %, Down went to the enemy damage and two Right arrows to 110 %, Escape closed it; `settings.ini` held both.

Evolution (22_DUNEB from the user's save, the user's mod set, test install): the menu's pad steps, the settings
file, Jack recognised as the shooter of his own shots (entity 1000000 through the player slot at +0x2C) and the
splat stain drawn (blend 1 306 0); no enemy came within reach of the runs, so its damage hooks have not scaled a
real hit yet (they read the same hit struct, explosion frame and player object as checked in the code).

With the keyboard mode on (RECOMP_KEYBOARD=1) a test run's main menu selection wandered by itself while the
user played the game on the same PC (likely their controller, read by the test instance too); without it the
menu stayed put, so the damage runs leave the keyboard mode out.
