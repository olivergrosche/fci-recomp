# Sounds

Found 2026-10-30 from both games' files; read and written with tools/soundbank.py. The layout is Ubisoft's
sound engine of the time (vgmstream's `ubi_sb.c` knows these versions as Far Cry Instincts' and Evolution's
Xbox banks); everything below was checked on the games' own files. Little endian throughout.

## Where they are

| File | Holds |
|---|---|
| `DVDsound.dat` (DAT2) | the sound banks, `\sounds_dvd\<bank>.sb2` (696 in Instincts, 581 in Evolution); a project file (version word, `BANK` at 8; not a bank); `\sounds_dvd\stream.ss2` (239 MB / 136 MB: Ubisoft's IMA ADPCM, stream type 3) |
| `sounds_xb\*.SS2` | streams the banks point into, raw Xbox ADPCM without headers: `GameCommon.SS2` (all weapons), `SingleMaps`, `MultiplayerMaps`, `M_MenuMusic` (Evolution: `gamecommon`, `fc15_singlemaps`, `fc15_multimaps`, `fc15_menumusic`, `m_menu_intromusic`) |
| `sounds_xb\<language>\*.LS2` | dialogue streams, a file per language. The dialogue banks come once per language: each one's offsets fit only its language's file (checked: 105-113 banks for each of the four) |
| `HDsound.dat` (DAT2) | 30 entries (Evolution 19) starting with the word 7, not analysed; Evolution's `\sounds_xb\fc15_m29_bar_s.ss2` is one (the XBE also names `Z:\HDSound.dat`, the hard disk's cache) |

A bank's name is the scripts' `soundbank` (or `LoadBank`) argument: `soundbank = 'Weapons_MP5'` is
`\sounds_dvd\weapons_mp5.sb2` (CRC-32 of the lower-case path, like every DAT2 name). The scripts' and the
XBE's strings name 114 of Instincts' banks, every weapon bank among them.

## Bank (.sb2)

| Offset | |
|---|---|
| 0x00 | version: 0x00150000 Instincts, 0x00170000 Evolution (same layout) |
| 0x04 | event count |
| 0x08 | resource count |
| 0x0C | data part count |
| 0x10 | size of the extra section |
| 0x14, 0x18 | -1, -1 |
| 0x1C | the events (0x48 bytes each), the resources (0x58 each), the extra section, the parts {id, size} (8 bytes each), then the data: the parts in that order |

Part 0 holds the sounds the hardware plays (Xbox ADPCM), part 1 software ones (Ubisoft IMA); a sound's
offset counts from its part's start. Weapon banks have part 0 only, or none when all their sounds stream.
Ids are the bank's group << 16 | a number (the MP5's bank is group 25: event 0x190008 = 1638408, the
`FireSoundEvent` of its script). Events and resources count apart: event 0xad0001 plays resource 0xad0000.

Event (0x48): 0x00 id, 0x04 type.

| Type | | |
|---|---|---|
| 1 | play | 0x08 the resource's index; 0x10 1.0 (16.16); 0x1C, 0x24, 0x28 distances in 16.16 (5, 50, 80 on the MP5's fire) |
| 4 | stop and play | 0x08 the index of an event to stop, 0x0C one to play, 0x10 0.1 or 0.15 (16.16, presumably the fade): the `FireEndSoundEvent` of all seven automatic weapons stops its `FireSoundEvent` and plays the burst's end |
| 2 | stop | 0x08 the index of the event to stop: the creatures' `IdleAndWalk_Stop` stops their `IdleAndWalk_Start` loop |
| 6, 7, 8, 10 | | not analysed |

Resource (0x58): 0x00 id, 0x04 type. Fields a type does not use hold leftovers (pointers, text).

| Type | | |
|---|---|---|
| 1 | audio | below |
| 3 | switch | 0x0C its table's offset in the extra section, 0x1C the count; entries {resource index, case} (8 bytes) |
| 4 | random | the same; entries {resource index, chance (65536 = 100 %), ?} (12 bytes) |
| 8 | silence | |
| 2, 5, 6, 7 | | not analysed |

Audio:

| Offset | |
|---|---|
| 0x08 | size of the data |
| 0x10 | offset: into the bank's part, or into the stream file |
| 0x14 | volume, dB in 16.16 (0xFFFD0000 = -3 dB) |
| 0x20 | flags: 0x08 streamed, 0x10 software (part 1), 0x400 loop; 0x80, 0x200 and 0x800 only on streamed ones; bits 0-2, 0x100 and 0xF000 on both (not known) |
| 0x28, 0x2C | frames and bytes; for a loop, those of its intro (0 in all but 9 loops per game) |
| 0x30, 0x34 | a loop's frames and bytes after the intro; else 0 |
| 0x38 | bytes a second: rate * 36 * channels / 64, rounded down |
| 0x3C | sample rate: 11025 to 48000 (the weapons' 22050 to 48000) |
| 0x40 | 16 |
| 0x44 | channels |
| 0x48 | stream type: 0 Xbox ADPCM, 3 Ubisoft IMA (stream.ss2) |
| 0x4C | offset of the stream file's name in the extra section (`GameCommon.SS2`), -1 for one in the bank |

Frames are whole blocks (a multiple of 64). Instincts has 630 sounds in banks, all mono Xbox ADPCM (31 loops),
and 24,546 streamed (957 stereo, 561 of them IMA in stream.ss2); Evolution 462 in banks (all mono, 33 loops)
and 27,159 streamed (546 stereo, 306 IMA). Every Xbox ADPCM
sound in a bank or in an SS2 file has valid block headers at its offset (630 + 2,505 in Instincts, 462 +
1,861 in Evolution; two names in Evolution's banks have no file, one of them is in HDsound).

Xbox ADPCM: a block of 36 bytes per channel, {int16 sample, u8 step index, u8 0} and 32 bytes of nibbles
in 4-byte words per channel in turn, low nibble first; 64 frames a block, the header's sample and 63
nibbles (the 64th is not played), as the runtime (src/xbr/xdk/dsound.cpp) and vgmstream decode it. The
tool's decoder gives the same samples as the MA5B extractor (napali-core, checked against ffmpeg's
`adpcm_ima_xbox`) for Halo's assault rifle sounds.

## The weapons' sounds

A weapon's sound is a tree: the play event's resource is a switch of two cases, 0 a mono sound in the bank
and 1 a stereo copy streamed from GameCommon.SS2 (the same sound: left and right correlate 0.9 and more),
each again a switch of two variants (a short and a long tail, 0.49 and 2.6 s on the MP5); reloads are a
random choice of two streamed sounds. Which case plays when was read from the content, not the code.

| Weapon | Bank (group) | Fire | After a burst | One shot | Reload | Equip |
|---|---|---|---|---|---|---|
| MP5 | weapons_mp5 (25) | 0x190008 loop | 0x19000a | 0x190002 | 0x190005 | 0xad0001 |
| M4 | weapons_carbine (6) | 0x60001 loop | 0x60002 | 0x60000 | 0x60005 | 0xad0001 |
| M16 | weapons_assaultriffle (109) | 0x6d0001 loop | 0x6d0002 | 0x6d0000 | 0x6d0008 | 0xad0001 |
| P90 | weapons_p90 (9) | 0x90001 loop | 0x90002 | | 0x90005 | 0xad0001 |
| Desert Eagle | weapons_eagle (2) | 0x20000 | | | 0x20002 | 0xac0001 |
| Beretta | weapons_92fs (70) | 0x460000 | | | 0x460002 | 0xac0001 |
| Beretta without suppressor | weapons_92f (839) | 0x3470000 | | | 0x3470002 | 0xac0001 |
| Glock | weapons_glock18 (100) | 0x640002 loop | 0x640003 | 0x640000 | 0x640006 | 0xac0001 |
| Benelli M1S90 | weapons_m1 (4) | 0x40000 | | | 0x40009, 0x40008, 0x40006 | 0x40003 |
| Barrett | weapons_m82a1 (0) | 0x6 | | | 0x3 | 0x4 (Evolution's script only) |
| SL8 | weapons_hksl8 (660) | 0x2940002 | | | 0x2940000 | 0x2940003 |
| M249 | weapons_m249 (5) | 0x50000 loop | 0x50003 | 0x50009 | 0x50008 | 0x50006 |
| M202 | weapons_m202 (110) | 0x6e0000 | | | 0x6e0003 | 0x6e0002 |
| Mortar (MK19) | weapons_mk19mod3 (114) | 0x720000 | | | 0x720001 | |
| Machete | weapons_machette (98) | 0x620001 (swing) | | | | 0x620004 |
| M67 | explosives_frag (93) | 0x5d0005 (explosion; 0x5d0006, 0x5d0007 bounces) | | | | 0x5e0005 (explosives_common) |

The Benelli's reload is three events: start, a shell, end. Akimbo pistols play a second gun's event
(0x20005, 0x460003, 0x3470003, 0x64000b). The equip sounds of the rifles (weapons_commonassault) and the
pistols (weapons_commonpistol) are one sound in one bank each; the trigger and empty clicks are
weapons_common's (0x450000, 0x450001, 0x450008). The M16's M203 has 0x6d0004 and 0x6d0006, the M202's
backblast 0x6e0004.

An automatic weapon's `FireSoundEvent` plays a loop of shots: 12 in 0.914 s on the MP5; the loops' shots are
66 to 85 ms apart, closer than the scripts' `fire_rate` (0.07 to 0.125 s). Its `FireEndSoundEvent` stops the
loop and plays the burst's end, a tail without a shot in it (peak -15 to -20 dB).

## Replacing (tools/soundbank.py)

A mod puts a bank at `mods\<mod>\DVDsound\sounds_dvd\<bank>.sb2`; the loader then merges all of DVDsound.dat
(252 MB in Instincts) into `mods\.cache`. The SS2 files lie outside the archives, so `replace` puts every
new sound into the bank's part 0, a streamed one too: the flags lose 0x08, 0x10, 0x80, 0x200 and 0x800, the
offset points into the part, the name becomes -1, and the sound is mono (no bank of either game holds a
stereo one). The sounds left alone keep their bytes and headers; only their offsets in the part move when
pieces no sound uses any more are dropped. Resources that end with the same data share it.

Checked: all 696 and 581 banks rebuild byte for byte, also through `replace` with nothing to replace;
`export` then `replace --from` of the unchanged WAVs gives the same bytes (weapons_mp5, weapons_m1,
weapons_commonassault); a replaced sound decodes to what went in with Xbox ADPCM's error only (17 to 33 dB
SNR on the Halo sounds).

Open: whether the engine plays a former stream from the bank in the game (a mono RAM voice where it had a
stereo stream; the largest built bank, 184 KB, is smaller than the game's own largest, 838 KB); the event
and resource types marked not analysed; HDsound's entries; stream.ss2's IMA format.

## Enemy voices

Found 2026-10-30 from both games' banks, the sound pack scripts in lua.dat and the levels' mission XML.

### The banks

The dialogue banks come once per language, `\sounds_dvd\<language>\<bank>.sb2` with `english`, `french`,
`german`, `italian` and `spanish` (the same events and resources in each; each one's offsets fit its
language's `.LS2`). Their sounds stream from `sounds_xb\<Language>\GameCommon.LS2` or `SingleMaps.LS2`
(Evolution: `fc15_pirates.LS2`, `fc15_rebels.LS2`, `fc15_ferals.LS2`), mono Xbox ADPCM at 16000 Hz; none
lies in the bank. The creatures' banks are not per language and stream from `GameCommon.SS2` at 24000 Hz, a
few sounds in the bank. The XBE names `Voices_Merc1` to `Voices_Merc9` itself (and `Voices_Merc%d`); the
level scripts load the others (`Sound:LoadBank('FC15_Barks_Pirate_1')`).

| Game | Bank | Group | Events, sounds | Whose |
|---|---|---|---|---|
| Instincts | `voices_merc1`, `_merc2`, `_merc3`, `_merc4`, `_merc6`, `_merc7`, `_merc9` | 540-543, 564, 565, 567 | 77-89, about 310 (570 s) each | the mercenaries' packs Merc1 to Merc10 |
| | `voices_ops1` to `_ops3` | 843-845 | 87-90, about 235 | packs OPS1 to OPS3 (heavy mercenaries) |
| | `voices_ubers1` to `_ubers4` | 873-876 | 2, 16 | packs Uber1 to Uber4 (Black Forest) |
| | `voices_<level>_generic_mercs`, `voices_se_*`, `se_*` | 207-228, 747-836 | | a level's scripted lines and conversations, 2 to 12 s (loaded by its script) |
| | `char_freak`, `char_sapper`, `char_chucker`, `char_uber` | 828, 650, 827, 829 | 18, 33, 34, 6 | the Trigens', the Chucker's and the Black Forest mercenaries' cries, pain, death, breathing |
| Evolution | `fc15_barks_pirate_1` to `_5` | 877-881 | 87, 376 | packs Pirate1 to Pirate5 |
| | `fc15_barks_rebel_1` to `_5` | 882-886 | 88, 381 | packs Rebel1 to Rebel5 |
| | `fc15_barks_feral_1` to `_3` | 887-889 | 24-25, 105-111 | packs Feral1 to Feral3 |
| | `fc15_char_feralwarrior` | 999 | 10, 9 | nine sounds of 3.5 to 4.4 s, played by nothing the scripts name |

A voice event plays a random choice of 1 to 11 lines, some with silence among them; an event that plays only
silence is a line the actor did not record (`voices_ops1` is silent on FIRST_HOSTILE_CONTACT and THREATEN).

### Who speaks with which bank

Each enemy of a level names a sound pack: `SoundPack="Merc6"` in `<Properties2>` of its `<Entity>` (also of
a `CreatureGeneratorSpawnSpot`) in the level's mission XML. A pack is a script,
`scripts\ai\packs\sound\<pack>.lua_compiled` in lua.dat (the AVAILABLE table lists them: Merc1-10, OPS1-3,
Uber1-4, Worker1-4, Chucker, Crowe, Dragon, Freak, Sapper; Evolution adds Pirate1-5, Rebel1-5, Feral1-3,
Doyle, Kade, Semeru, WorkerEx1-4):

    SOUNDPACK.Merc1 = { FRIENDLY_FIRE = { Priority = 50, soundEventID = '35389442' }, ... }

(Evolution's add `Relevance`; their names start with `MPACK_`). The id is an event of a bank, its group the
bank: Merc1 and Merc5 speak with `voices_merc1`, Merc2 and Merc8 with `_merc2`, Merc3 and Merc10 with
`_merc3`, the others with their own. Packs name other banks' events too (Merc4 one of `_merc1`'s, OPS3
three of group 841's, Pirate5 some of Pirate4's, Feral2 and Feral3 some of Feral1's): the engine plays any
loaded bank's event. The AI calls a pack event by name (`AI_DIES`, `GRENADE_SEEN`) with its priority; the
model plays no part. Entities by model and pack in the campaign levels:

| Game | Model | Packs |
|---|---|---|
| Instincts | `merc_prtoto01` (870), `merc_kit_03` (197), workers and scientists (30) | Merc1 to Merc10, spread evenly over all of them (a few with none) |
| | `merc_kit_04` (109) | OPS1 to OPS3 (104), Merc1 and Merc4 (3) |
| | `uber_kit_01` (46) | `Uber` (36: no such pack, they say nothing), Uber1 to Uber4 (8) |
| | `freak_sapper_kit_01` (199), `chucker` (7) | Freak (73), Sapper (62); Chucker (6) |
| | `crowe`, `doyle`, `krieger` | Merc1 (7), Merc9 (1) |
| Evolution | `pirate_kit_01` (662), `_02` (87), `_03` (59) | Pirate1 to Pirate5 |
| | `rebel_kit_01` (156), `_02` (20), `_03` (168) | Rebel1 to Rebel5 (a few Pirate packs) |
| | `feral_warrior_kit_02` (26), `_03` (44) | Feral1 to Feral3 |

So a voice set follows a pack family, and a family serves all models of its faction: Instincts' common
mercenaries and kit 3 share the Merc packs, Evolution's three pirate kits the Pirate packs.

### The events

The packs' names say what each event is for (87 in a Merc pack, 84 in a Pirate pack, 23 in a Feral pack):

| Kind | Merc and OPS packs | Pirate, Rebel and Feral packs (`MPACK_...`, with `_FORMATION`, `_LEADER` and alert level `_GREEN` to `_RED` variants) |
|---|---|---|
| alert, spotting | FIRST_HOSTILE_CONTACT, IDLE_TO_THREATENED(_GROUP), IDLE_TO_INTERESTED(_GROUP), PATROL_AWARE | FIRST_HOSTILE_CONTACT, SOMETHING_SEEN, IDLE_TO_INTERESTED, IDLE_TO_THREATENED, MERC_SAW_DOYLE |
| search, lost, found again | ENEMY_TARGET_LOST, ENEMY_TARGET_REGAIN | ENEMY_TARGET_LOST, ENEMY_TARGET_REGAIN, FIND_BACK_TARGET |
| calming down | THREATENED_TO_IDLE, INTERESTED_TO_IDLE, *_IDLE_RESPOND | INTERESTED_TO_IDLE |
| answers, orders | ORDER_RECEIVED, *_RESPOND_GROUP, TEAM_LEADER_ORDER_*, TEAM_RADIO_*, SPECOPS_DIRECTIONNAL_* | SLOT_REPLACEMENT_*, SLOT_LOSS_*, THREATEN_..._FLANKLEFT/REAR/DEFEND, PLAY_DEFENSE, GIVE_SUPPORT_FIRE |
| callouts | AI_CALLOUT_*, CALL_REINFORCEMENTS, PLAYER_STEALS_*, AGAINST_VEHICLES | AI_CALLOUT_CLOSE_COMBAT, MERC_VEHICLE_DANGER, PLAYER_STEALS_* |
| attack, taunts | THREATEN, MACHINEGUN_ATTACK, UBER_TAUNTS | THREATEN, MACHINEGUN_ATTACK, SNIPER_THREATEN, MERC_NO_HIDING_PLACE, FERALJUMP |
| grenades | GRENADE_SEEN, FIRE_IN_THE_HOLE | GRENADE_SEEN, GRENADE_EXPLOSION, FIRE_IN_THE_HOLE |
| shot at, hurt | GETTING_SHOT_AT, FLASHBANG/GAS_GRENADE_EFFECT | BULLET_RAIN, RECEIVING_DAMAGE |
| fear | ACT_AFRAID(_GROUP), SPECOPS_VS_ABERRATIONS | THREATEN_..._LO_HEALTH, DISORGANIZE_FORMATION, SLOT_LOSS_NOONE_NEAR |
| death | AI_DIES, FERAL_DEATH, BURNING, CAUGHT_IN_TRAP | AI_DIES, AI_DIES_BURNING, FERAL_DEATH, CAUGHT_IN_TRAP |
| friends, kills | FRIEND_DEATH, DEAD_BODY_FOUND, FRIENDLY_FIRE, AI_DOWN_CARVER, SATISFACTION_* | the same, MERC_KILLED_DOYLE |

The workers' packs (Worker1-4) use four events of the Merc banks (`AI_DIES_WORKER` is AI_DIES). Some names
point at events no bank has (the Merc packs' SPECOPS_* and UBER_*, FLASHBANG, GAS): they say nothing. A few
events of each bank are played by no pack (`voices_merc1` 0x21c0062 to 0x21c006d, 1 to 37 s): scripted.

The creatures' scripts name their events: `LightHurt`, `HeavyHurt`, `Death`, `IdleAndWalk_Start` and
`Run_Start` (loops, stopped by `IdleAndWalk_Stop` and `Run_Stop`), and the packs SCREAM, BITE (Freak),
INVESTIGATE, DIE_SCREAM, DIE_180_SCREAM (Sapper), ENRAGED, PUNCH_FORWARD/BACKWARD, HITGROUND, CHARGE, DEATH
(Chucker); the sapper's `ExplosionEvent`. Their other events (footsteps, attacks) are played from the
animations; not identified.

### Conversations

Found 2026-10-31 from both games' mission XML. The enemies' conversations are AI anchors: an
`<Object Type="AIAnchor" Name="..." NextAnchor="...">` holds `<Say>` steps, each with a
`<PlaySound ID="13697030" Wait="1"/>` (the next step waits for the line to end; `TimeShift` delays a step):

    <Say><PlaySound ID="13697030" Wait="1" /></Say>                          the anchor's user speaks
    <Say Target="Merc_Beginning_8_a" TimeShift="0.3"><PlaySound ID="13697032" Wait="1" /></Say>

A PlaySound outside a Say is the anchor's user's as well. An anchor's users are the entities naming it
(`FirstAnchor`, `OnPlayerSeenAnchor`, a spawn spot's `FirstAnchor1`), reaching it by other anchors'
`NextAnchor`, or sent to it by a trigger (`<EventTarget Target="<EntityId>" Event="SwitchToGenericJob"
ExtraParam="AIAnchor_...">`); a speaker's model is in the level's dependency list, its pack in its entity.
The lines played this way:

| Banks | Lines | Played by |
|---|---|---|
| `voices_<level>_generic_mercs` (Instincts 01b, 02, 03, 04, 05, 07, 10, 11) | 29 to 69 a level, 0.5 to 12 s | conversations of mercenaries (common and kit 3, any Merc pack); the rest of each bank no anchor plays |
| `voices_14_generic_specops` (level 13) | 20 | the heavy mercenaries (OPS packs) |
| `voices_01a_generic_workers` | 45 | workers (no anchor in the levels) |
| `voices_merc1`, `_merc2`, `_merc3` (events no pack names, 0.7 to 37 s) | 5, 3, 6 | mercenaries at anchors (monologues) |
| `se_*`, `voices_se_*` (Instincts), `fc15_se_*` (Evolution; `_ad` banks mostly the enemies') | a few each | mixed: mercenaries, pirates, rebels, ferals beside Crowe, Valerie, Doyle, the femme fatale, Krieger, scientists, workers, the hacker |
| `voices_gen_crowe`, `voices_krieger`, `voices_gen_carver`, radio and announcer banks | | named people; most lines by no anchor |

Most lines of the `se_*` banks are played by no anchor and no script by id: the scripted scenes play them from
their animations (the `_se` animation lists); who speaks them is not in the data.

The lines' text is in common.dat's string tables (`<stringtable language="english">`, section `Subtitles`:
`<string enum="63373316" value="Stupid bar keep.\nTelling me I'm drunk. ..."/>`, the enum the event id),
without the speaker; it tells the scenes' enemy talk from Jack's, Doyle's and the femme fatale's lines.

Counted by speaker, and for 56 scene lines by their subtitle (fci-modsrc `halo/voices/chatter.py`):
Instincts 488 lines of enemies in 27 banks, 638 kept (people, civilians, unknown speakers, scenes);
Evolution 137 in 21 banks, 528 kept.

### Replacing them

The `.LS2` files lie outside the archives, so a mod puts new voices into the bank (`replace`, as with the
weapons; `soundbank.py` names a dialogue bank `english/voices_merc1`, reads its streams from its language's
folder, and a `cache` given to `replace` encodes a sound once for all five languages). A family's banks are
loaded together (the XBE's Voices_Merc list; the levels load all five pirate or rebel banks, the tutorial
Rebel 1, 3 and 5, level 22 Rebel 1 to 3), so the Halo voice mods (fci-modsrc `halo/voices/build.py`) fill
only the first bank of a family and point the other packs at its events: each pack's soundEventID strings,
rewritten in place (the same length: the script keeps its size and code). The new data is then held once,
0.15 to 0.94 MB in one bank (the game's own largest is `voices_gen_crowe`, 838 KB, 28 sounds in the bank).

A conversation bank is a level's, and its lines run to minutes (146 s in `voices_02_generic_mercs`). Every
Xbox ADPCM block decodes on its own, so a sound may be any whole-block stretch of another one's data:
`replace(..., windows={sound: (rate, tape, start, frames)})` stores a tape once and makes each sound a
stretch of it (the runtime plays a buffer where its data lies, `SetBufferData` copies nothing). The voice
mods give each line a window of its own length into about 14 s of Covenant chatter per bank, cut at the
phrases' edges, the next line from where the last stopped: 27 to 170 KB in a bank instead of the minutes.

Open: whether those banks fit the game's sound memory (64 MB Xbox, in every level); the scripted scenes'
lines (whose speakers the data does not name); the creatures' animation sounds; what plays
`fc15_char_feralwarrior`.
