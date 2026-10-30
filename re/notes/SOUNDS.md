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
| 2, 6, 7, 8, 10 | | not analysed |

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
