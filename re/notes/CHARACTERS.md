# Characters

Found 2026-10-30 from both games' level archives (every `.xbg` under `animations\characters\`, 546 models
of which 80 are skinned) and the levels' dependency lists; the format is in MODELS.md, read and written with
tools/xbg.py. Goal: enemies replaced by other models (mercenaries by Covenant Elites, Trigens by the Flood).

## Who is where

Every level archive holds an XML list of its entities (`<Entity Class="Merc" Name="..."><File Name=...>`)
with the files each needs: body model, hat, animation list (`.xba`), effects. Counts are entities plus
spawn spots (`CreatureGeneratorSpawnSpot`) in the campaign levels. The multiplayer maps list no characters;
`specops01`, `point02`, `scientist03`, `mp_uber`, `pirate_kit_mp` and `rebel_kit_mp` (in every archive)
are the multiplayer models.

| Instincts | Class | Model (`animations\characters\...`) | Levels |
|---|---|---|---|
| mercenary (most common) | Merc | `mercenaire\merc_kit_01\merc_prtoto01` | 00 to 07, a few in 10 |
| mercenary | Merc | `mercenaire\merc_kit_03\merc_kit_03` | 02, 03, 05, 06, 07, 10, 11, 13 |
| mercenary, heavy | Merc | `mercenaire\merc_kit_04\merc_kit_04` | 11, 13 |
| mercenary, Black Forest | Merc | `mercenaire\uber_kit_01\uber_kit_01` | 13 |
| Trigen (freak / sapper) | Freak, Sapper | `freak_sapper_kit_01\freak_sapper_kit_01` | 07, 10, 11, 13 |
| Trigen (chucker) | Chucker | `chucker\chucker` | 06, 10, 11 |
| Trigen (old sapper) | Merc | `sapper\sapper` | 10 (one) |
| named | Merc | `mercenaire\crowe`, `crowemutant`, `doyle`, `krieger` | 01 to 13 |
| workers | Worker | `mercenaire\worker_kit_01`, `scientist_kit_01`, `hacker` | 03-07, 11 |
| others | Valerie, Dragon, Birds, Fish | `valerie`, `dragon\dragon03` (lizard), `seagull`, `parrot_multi`, `fish`, `jellyfish` | |

| Evolution | Class | Model (`animations\characters\mission_pack\characters\...`) | Levels |
|---|---|---|---|
| pirates | Merc | `pirate\pirate_kit_01` (most), `_02`, `_03` | 21 to 26 |
| rebels | Merc | `rebels\rebel_kit_01`, `_02`, `_03` | 22, 28, 29, 30 |
| feral warriors | Merc | `feral_warrior\feral_warrior_kit_02`, `_03` | 22, 29, 30 |
| named | Merc | `rebel_leader`, `rebel_sub_boss`, `doyle`, `magistrat`, `barman`, `prisoner` | |
| femme fatale | Valerie | `femme_fatale\ff_kit_01`, `ff_naked` | 21 to 30 |
| tutorial (20) | Merc, Worker | Instincts' mercenaries (`mercenaire\...`), `freak_sapper_kit_01` | 20 |

Every Merc and Worker, pirates and rebels too, uses one animation list, `mercenaire\merc01.xba`
(`merc01_se.xba` in scripted scenes); the Trigens have `freak.xba`, `sapper.xba` (one model for Freak and
Sapper) and `chucker.xba`. For the Halo mod: the Merc class (mercenaries, pirates, rebels) becomes Elites,
Freak, Sapper and Chucker the Flood.

## Models

Triangles of the LOD 0 / LOD 1 meshes; humans are about 1.80 m tall, feet at 0.

| Model | Bones | Triangles | Textures | Parts besides the mesh |
|---|---|---|---|---|
| merc_prtoto01 (Instincts) | 57 | 2528 / 490 | 21 | BODY_ARMOR_HIGH (296), BODY_ARMOR_LOW (112) |
| merc_kit_02, _03, _04 | 57 | 2926 / 607, 2975 / 624, 2632 / 611 | 24-28 | the same armour parts (Instincts only) |
| uber_kit_01, mp_uber | 57 | 2169 / 504 | 17 | |
| freak_sapper_kit_01 | 46 | 2429 / 567 | 10 | |
| chucker | 51 | 1456 | 6 | no LOD 1; 2.9 m tall |
| sapper | 45 | 1688 | 4 | no LOD 1 |
| pirate_kit_01, _02, _03 | 57 | 3174 / 801, 2590 / 625, 2395 / 560 | 23-30 | |
| rebel_kit_01, _02, _03 | 57 | 2643 / 653, 2608 / 702, 2800 / 716 | 20-23 | |
| feral_warrior_kit_02, _03 | 61 | 2324 / 688, 2631 / 774 | 13-15 | |
| specops01, point02, scientist03, krieger, doyle | 57 | 1450-1721 | 5-17 | MPLOGO (50-66): the team logo plates |
| crowe, crowemutant, valerie, worker, scientist_kit_01 | 57-59 | 1990-2412 | 7-15 | |

The diffuse maps are DXT5 (a few DXT1), 16 to 512 pixels a side, one per piece of clothing or skin; the
bump maps (`_nt`) DXT1 normal maps (mean blue about 250), a few 8-bit height maps. Materials and shaders are
in MODELS.md.

## Skeletons

All humans are 3ds Max Biped rigs: Carver's third-person model has the 41 body bones, the mercenaries add 12
face bones and 4 roll bones (57); Trigens drop face bones, others add some. Skinned vertices never use
`BIP01` or `Bip01_FaceRoot` (they have no skin matrix).

| Bones | Models | Compared with the 57 |
|---|---|---|
| 57 | mercenaries, pirates, rebels, named humans | `merc_kit_03` (fingers) and `crowe` (eyes) number some bones differently |
| 61 | feral warriors | + `RollBone_UID_01` to `_04` |
| 61 | femme fatale | + `Bip01_B Hairs`, `L Hairs`, `R Hairs`, `Bip01_Breast` |
| 59 | valerie | + `Bip01_ EyeManipulator`, `Bip01_ EyeTarget` |
| 51 | chucker | no lip and eyelid bones |
| 46, 45 | freak_sapper_kit_01, sapper | no face bones but the jaw (46), none (45) |
| 41 | carver_3rd | no face and roll bones |

The bind pose is a T-pose (arms out along x, a little down), facing -y, +x the character's left, z up,
metres. The body bones of all 57-bone models agree within 1 mm and 0.1 degrees, but for the rebels' neck
(18 degrees); face bones (eyebrows, jaw, eyes) differ by up to 4 cm and 16 degrees. Each model's skin
matrices fit its own. The 57 bones of `specops01` (number, parent, skin matrix, place in the model):

| # | Bone | Parent | Skin | At | # | Bone | Parent | Skin | At |
|---|---|---|---|---|---|---|---|---|---|
| 0 | BIP01 | - | - | 0, -0.045, 0.955 | 29 | Bip01_L Forearm | 28 | 27 | 0.388, 0.045, 1.343 |
| 1 | Bip01_Pelvis | 0 | 0 | the same | 30 | Bip01_L Hand | 29 | 28 | 0.602, -0.061, 1.234 |
| 2 | Bip01_L Thigh | 1 | 1 | 0.115, -0.045, 0.955 | 31-33 | Bip01_L Thumb01-03 | 30, 31, 32 | 29-31 | |
| 3 | Bip01_L Calf | 2 | 2 | 0.141, 0.018, 0.542 | 34-36 | Bip01_L Index01-03 | 30, 34, 35 | 32-34 | |
| 4 | Bip01_L Foot | 3 | 3 | 0.167, 0.097, 0.104 | 37-39 | Bip01_L Fingers01-03 | 30, 37, 38 | 35-37 | |
| 5 | Bip01_L Toe | 4 | 4 | 0.197, -0.043, 0 | 40 | Bip01_L Forearm RollBone | 29 | 38 | |
| 6-9 | Bip01_R Thigh, Calf, Foot, Toe | 1, 6, 7, 8 | 5-8 | x mirrored | 41 | Bip01_L UpperArm RollBone | 28 | 39 | |
| 10 | Bip01_Spine | 0 | 9 | 0, 0.016, 1.031 | 42 | Bip01_R Clavicle | 12 | 40 | |
| 11 | Bip01_Spine1 | 10 | 10 | 0, 0.024, 1.165 | 43 | Bip01_R UpperArm | 42 | 41 | |
| 12 | Bip01_Spine2 | 11 | 11 | 0, 0.043, 1.325 | 44 | Bip01_R Forearm | 43 | 42 | |
| 13 | Bip01_Neck | 12 | 12 | 0, 0.058, 1.522 | 45 | Bip01_R Hand | 44 | 43 | |
| 14 | Bip01_Head | 13 | 13 | 0, 0.061, 1.610 | 46-48 | Bip01_R Thumb01-03 | 45, 46, 47 | 44-46 | |
| 15 | Bip01_FaceRoot | 14 | - | the same | 49-51 | Bip01_R Index01-03 | 45, 49, 50 | 47-49 | |
| 16 | Bip01_Jaw | 15 | 14 | 0, 0.011, 1.653 | 52-54 | Bip01_R Fingers01-03 | 45, 52, 53 | 50-52 | |
| 17 | Bip01_LowerLip | 16 | 15 | | 55 | Bip01_R Forearm RollBone | 44 | 53 | |
| 18-20 | Bip01_UpperLip, R Lip, L Lip | 15 | 16-18 | | 56 | Bip01_R UpperArm RollBone | 43 | 54 | |
| 21-24 | Bip01_R/L EyeBrow, R/L EyeLid | 15 | 19-22 | | | | | | |
| 25, 26 | Bip01_L Eye, R Eye | 14 | 23, 24 | | | | | | |
| 27 | Bip01_L Clavicle | 12 | 25 | 0.041, -0.023, 1.486 | | | | | |
| 28 | Bip01_L UpperArm | 27 | 26 | 0.191, 0.036, 1.443 | | | | | |

## Animations

Ubisoft's MORE system, all files `ubi/b0-l` followed by a class name:

| File | Class | Holds |
|---|---|---|
| `<list>.xba` | (text) | `#Name`, the extension, folders (`>n<` = under folder n), then `alias=>folder<file` lines: the AI's names for the clips (935 in `merc01.xba`) |
| `.mcl.mrg.bin` | `MORE::Clip` | speed, weight, blend time and the path of a `.man` |
| `.man.mrg.bin` | `MORE::AnimationStatic` | the keys (format not decoded) |
| `.mac.mrg.bin` | `MOREActor::ActorModel` | one next to each model: its bones by name and the channels animated on them |

The mercenary actor animates `Bip01` position (x, y, z) and rotation, the other body bones' rotations
(knees, elbows and finger joints about z only), positions of face and roll bones in some models, and nodes
that are not bones of the model: `Prop01`, `Prop02` (where the weapons go) and `Merc EventEmitter`. So the
bone lengths come from the model, the height of the pelvis from the animation.

## Attachments

- Hats are their own rigid one-bone models (`hats\*.xbg`, each with an actor model), stored in the frame of
  `Bip01_Head` (placed there they sit on the head); the level's entity list gives each Merc its hat.
- Body armour: the parts BODY_ARMOR_HIGH and BODY_ARMOR_LOW of Instincts' merc kits (skinned like the body,
  the game shows one of them).
- Weapons hang on the actor's Prop nodes, not on bones of the model.

## Physics

The tail of a character model (after the vertex data, to the end of the file) holds its physics objects,
48 in the mercenary: a count, then objects with a type hash and a name (`BIP01_L CALF PHYSCAPSULE`,
`BIP01_HEAD PHYS`, `BIP01_SPECIALVERT HEADFRONT PHYSSPHERE`, `BIP01_RAGDOLL PHYS`, `... ATTACH PHYS`,
`... MINDIST PHYS`): capsules on the body bones (hits), spheres, ragdoll joints and limits. Not decoded;
xbg.rebuild_skinned copies it unchanged. The 13 bones with a ragdoll body (header 0x50) are BIP01,
pelvis, thighs, calves, Spine1, Spine2, head, upper arms and forearms.

## What an importer must respect

- Keep the template's skeleton (bone numbers, names, bind pose): the skin matrices, actor model, animations,
  physics and ragdoll all follow it. Fit the new mesh to it in the T-pose; a taller creature keeps human
  hit capsules and the animated pelvis height (about 0.95 m).
- Skin only to bones with a skin matrix (not `BIP01`, not `Bip01_FaceRoot`); at most 2 bones per vertex
  (weights in 1/255); at most 8 bones per submesh (rebuild_skinned splits the mesh to fit).
- Positions are int16 in the root's frame: +-1 m around the pelvis at the usual scale 1/32767. A bigger
  model needs a larger scale (header 0x9C; rebuild_skinned's scale).
- Texture coordinates within the model's range (header 0xA0: 0 to 1 in most, -1 to 4 in some).
- Use the template's materials: the shader decides the vertex size (28 bytes with a tangent frame, 32 with
  the colour mask, 20 with a normal only). Textures are swapped in the archive (tools/dat2.py).
- Give both LOD parts a mesh (LOD 1 may be the same). Keep or replace the armour and MPLOGO parts.
- No hats on an Elite: change the entities' hat files or replace the hat models.

## Open

- The physics objects' layout (capsule sizes and frames), needed if a model outgrows human proportions.
- What the colour of 32-byte vertices selects (shader 4507): almost always exactly one of r, g, b, a at
  255.
- The `.man` key format; whether the animations ever set body bone positions.
- Rebuilt characters are checked offline (all 80 skinned models re-encode to the same bind-pose and posed
  geometry); none has been loaded in the game yet, in particular one whose submesh table grew.
