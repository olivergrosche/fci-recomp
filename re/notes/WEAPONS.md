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
