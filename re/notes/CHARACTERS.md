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

## Importing a character (tools/character_import.py)

Started 2026-10-30 with Halo CE's bipeds (glTF exports of the user's maps: skinned, joints = Halo nodes in
their bind pose, Halo units, Y up through a root node, facing +Z; `"axes": ["x", "-z", "y"]` and
`"scale": 3.048` give the game's axes in metres). A config names the source, the template model, the fit and
the texture options; the tool reads the templates out of the game's level archives (read only), writes the
rebuilt model, its two textures and the hidden hats into a mod folder for each level archive that holds the
model (a pattern such as `levels/[0-9]*` leaves out the multiplayer maps, which carry the merc models
unused), and a `mod.ini`.

**Mapping.** Halo CE's bipeds are Character Studio rigs too, and their local axes follow the same
conventions as the games' Biped (x along the bone, z the hinge of knees and elbows, the pelvis x up and z
left; checked joint by joint on the elite: same directions within a few degrees once posed alike). Joints
map by name (case, spaces and underscores aside); a joint without a bone moves with its nearest mapped
ancestor and gives it its weights. For the elite (the Flood combat forms have the same body names):

| Halo joint | Bone | Fit |
|---|---|---|
| bip01 pelvis | Bip01_Pelvis | frame |
| bip01 spine | Bip01_Spine | aligned to spine1, length x 0.96 |
| bip01 spine1 | Bip01_Spine1, Bip01_Spine2 | aligned to neck, x 0.91; weights shared with Spine2 along the length |
| bip01 neck, neck1 | Bip01_Neck | aligned to head, x 0.54 (the elite's long forward neck stands up, 9 cm) |
| bip01 head, frame mandible (4) | Bip01_Head | keep (the face looks ahead), size 0.85, 7 cm up and 2 cm back |
| bip01 l/r clavicle | Bip01_L/R Clavicle | aligned, x 0.54 (no vertex of the elite uses them) |
| bip01 l/r upperarm | Bip01_L/R UpperArm | aligned, x 0.56, turned 52 degrees (arms down -> T-pose), size 0.7 |
| bip01 l/r forearm | Bip01_L/R Forearm, Forearm RollBone | aligned, x 0.60, the far part on the roll bone |
| bip01 l/r hand | Bip01_L/R Hand | frame, size 0.75 (no finger bones: the hands stay rigid) |
| bip01 l/r thigh | Bip01_L/R Thigh | aligned, x 0.69, turned 41 degrees |
| bip01 l/r calf, horselink | Bip01_L/R Calf | aligned to the foot, x 0.56: the backward horselink bend stays in the shin |
| bip01 l/r foot | Bip01_L/R Foot | frame, size 0.7, grounded (+0.13 m: the hoof stands on the floor) |
| Flood: frame antenna (9), spike (9), bip01 ponytail1 | with spine1, l forearm, head | |

Toes, the upper arm roll bones, jaw and face bones and the fingers get no weights.

**Conforming.** Each mapped joint gets a map from the source's bind pose into the template's: an aligned
joint (its mapped child lies along its x axis, on a descendant of its bone) turns its joint-to-child
direction onto its bone-to-child-bone direction with the hinge axes matched, stretches by the length ratio
between the two joints only (what hangs past either end, such as the Flood's tentacle spikes, keeps its
size) and scales across by the thickness; a frame joint carries its local frame onto the bone's, a keep joint
keeps the source's orientation; both scale evenly. Each joint lands on its bone (plus an offset), its child
on the child's bone, so neighbouring maps agree at the joints. A vertex is the weighted blend of its joints'
maps (linear blend, as a pose moves it); its normal follows the blended map's inverse transpose; tangent
and binormal are recomputed from the atlas coordinates. Grounded bones move up until their lowest vertex
stands on the template's floor, their aligned parent stretching to meet them. Weights go to the joints'
bones (shared along the length where template bones lie between), the two largest are kept, renormalised.
Elite at thickness 0.8: legs keep the human hip height (0.955 m), the torso the elite's length, the crest
ends 1.94 m up (spec-ops elite 2.03 m; pirate_kit_01 1.83 m).

**Textures.** The glTF materials (transparent ones left out: the elite's inset lights, the Grunt's, the
Jackal's shield, the Flood's fronds) go into one atlas at their own resolution (elite and Jackal 1024 x 512,
Grunt, Flood, Hunter, spec-ops elite 512 x 512, DXT5, all mip levels): base colour plus emission, gain 1.6
(Covenant) / 1.15 (Flood) with a soft roll-off, a dark matte in the alpha-tested holes (teeth, Jackal head),
gloss 126 to 155 as alpha (the pirates' own range). The whole mesh is one 28-byte material of the template;
the atlas and a flat 64 x 64 normal map go into two of the template's texture files and the material is
pointed at them (`"texture": {"diffuse", "bump"}`). The level's dead bodies and props share many of those
files (`deadmerc_*` wear the mercenaries' trousers, `dead_pirate_*` the pirates' `id01a`), and the rebels'
or pirates' kits share their normal maps, so each model writes files that only it uses where it has any (a
file list per level names each model's textures, so new file names are avoided). Both LOD parts get the
full mesh; body armour parts get one triangle of no area; hats are replaced by models whose triangles have
no area.

| Template, material | Atlas in | Flat normals in | Other users of those files |
|---|---|---|---|
| merc_prtoto01, 1 | `merc_kit_01\pants_df` | `pants_nt` | deadmerc_chair, deadmerc_floor (it has no file of its own) |
| merc_kit_03, 1 | `merc_kit_03\vest_df` | `poches_df` | none |
| merc_kit_04, 2 | `helm_mask_df` | `helm_mask_nt` | none |
| uber_kit_01, 0 | `uber_kit_01_df` | `uber_kit_01_nt` | mp_uber (multiplayer) |
| freak_sapper_kit_01, 1 | `freak_sapper_vest_df` | `freak_sapper_vest_nt` | none |
| chucker, 1 | `chucker_df` | `chucker_no` | none |
| pirate_kit_01, 0 | `pirate\id01a` | `pirate\id12nt` | dead pirates only (`id01ant` is kits 2 and 3's) |
| pirate_kit_02, 0 | `id01b` | `id01bnt` | dead_pirate_08 |
| pirate_kit_03, 0 | `id16` | `id16nt` | none |
| rebel_kit_01, 1 | `rebels\id03b` | `id03nt` | booniehat02 (worn by nobody); `id01a`, `id01nt` are kit 2's too |
| rebel_kit_02, 0 | `id01c` | `id02b` | none |
| rebel_kit_03, 1 | `id01b` | `id02a` | none |
| feral_warrior_kit_02, 1 | `feral_warrior\id01c` | `id04b` | none |
| feral_warrior_kit_03, 6 | `id05` | `id05nt` | none |

**Other creatures.** The Grunt, Jackal and Hunter are Character Studio rigs as well (17, 27 and 30 joints).

- *Grunt* (1.32 m to the head, hips at 0.5 m, a hunched spine leaning 34 degrees forward, bow legs, no hand
  joints). The legs have to reach from FCI's hips (0.955 m) to its feet, so they stretch 1.5 times; at
  thickness 2.0 (thighs), 1.4 (calves), 1.3 (feet) they stay stocky instead of human sticks, knees and feet
  offset 10 and 8 cm outward (along the bones' hinge axes, so knee and hip swings do not move them) keep the
  bow legs. Straightening the spine tips the methane tank back to the horizontal; `reshape` turns the tank
  (spine1's vertices behind y = 0.08) 35 degrees forward about its base first, so it stands up-back as in
  Halo. The fist (forearm vertices past 0.40 m) becomes a joint on the hand bone (`joints`), so the forearm
  fits FCI's and the weapon sits in the fist. Torso 1.1 / 1.0 / 0.9 (pelvis, spine, spine1), arms 1.3 / 1.25,
  head 1.2, 12 cm down and 3 cm forward. It stands 1.82 m to the tank's tip, its head 1.31 to 1.76 m: a big
  Grunt (shorter legs would leave the feet in the air or the hips off the bones). The game draws it at 0.77
  (`entity_scale`, below): 1.40 m to the tank's tip, the head at 1.0 to 1.36 m, as Halo's. In poses that hold a
  weapon close (forearms across the belly) the arms vanish in the shell: its chest is wider than a human's.
- *Jackal* (digitigrade like the elite: thigh forward, calf back to the horselink, which merges into the
  calf as the elite's; hips at 0.996 m, quills 2.10 m). Thickness 0.9, hands and feet 0.9, head 1.05 moved
  8 cm forward and 4 cm down (it juts out as in Halo); 2.0 m to the quills. The energy shield (BLEND,
  "frame shield") is left out; the wrist generator stays.
- *Hunter* on the Chucker (2.95 m, hips at 1.58 m; the Chucker's at 0.96 m with splayed legs and a huge right
  arm). Thighs and shins squash to 0.73 and 0.60 of their length, which suits the Chucker's crouch; the fuel
  rod cannon arm lands on the huge right arm, the shield arm on the left. Thickness 1.1, legs 1.2, 2.8 m
  tall. The Flood combat elite on the Chucker stays a stretched stick (thin limbs, sunken head), and the
  carrier form has no Biped joints and only stubs of arms for the throwing arm: neither is used.

**Mods.** One mod per FCI model and Halo creature, so the game's menu (which keeps only one of two mods that
replace the same file) chooses per enemy: `halo/characters-instincts.json` and `characters-evolution.json`
in fci-modsrc, each with its creatures and mods; `halo-hats-off` hides the hats separately, as the common
mercenaries and kit 3 (Instincts) and all pirates, rebels and feral warriors (Evolution) share them. The
importer refuses a config whose mods for different models write one file.

| Game | FCI model | Mods (default on first) |
|---|---|---|
| Instincts | merc_prtoto01 | `halo-elite-merc-common` (Elite minor); `halo-grunt-merc-common`, `halo-jackal-merc-common` |
| | merc_kit_03 | `halo-jackal-merc-kit03` (Jackal minor); `halo-elite-merc-kit03`, `halo-grunt-merc-kit03` |
| | merc_kit_04 | `halo-elite-merc-heavy` (Elite major); `halo-grunt-merc-heavy`, `halo-jackal-merc-heavy` (majors) |
| | uber_kit_01 | `halo-elite-specops-uber` |
| | freak_sapper_kit_01 | `halo-flood-trigen` (Flood combat human) |
| | chucker | `halo-chucker-hunter` |
| | hats | `halo-hats-off` (beret01, fatiguecap01, rangerhat01 in 00 to 13) |
| Evolution | pirate_kit_01 | `halo-elite-pirate-kit01`; `halo-grunt-pirate-kit01`, `halo-jackal-pirate-kit01` (minors) |
| | pirate_kit_02 | `halo-elite-pirate-kit02`; `halo-grunt-pirate-kit02`, `halo-jackal-pirate-kit02` (majors) |
| | pirate_kit_03 | `halo-grunt-pirate-kit03`; `halo-elite-pirate-kit03`, `halo-jackal-pirate-kit03` (minors) |
| | rebel_kit_01, _03 | `halo-jackal-rebel-kit01`, `-kit03`; `halo-elite-`, `halo-grunt-rebel-kit01`, `-kit03` (minors) |
| | rebel_kit_02 | `halo-jackal-rebel-kit02`; `halo-elite-rebel-kit02`, `halo-grunt-rebel-kit02` (majors) |
| | feral_warrior_kit_02 | `halo-grunt-feral-kit02`; `halo-elite-feral-kit02`, `halo-jackal-feral-kit02` (minors) |
| | feral_warrior_kit_03 | `halo-grunt-feral-kit03`; `halo-elite-feral-kit03`, `halo-jackal-feral-kit03` (majors) |
| | hats | `halo-hats-off` (beret01 in 21 to 30) |

**Size (entity scale).** The skeleton and its animations fix the height (hips at 0.955 m), so a smaller
creature is a smaller entity, not a smaller mesh. BasicAI (`scripts\default\entities\ai\basicai.lua`,
both games, the same code) ends OnReset with `if self.PropertiesInstance.fScale then
self:SetStatObjScale(self.PropertiesInstance.fScale) end`; SetStatObjScale (Evolution 00185D43) stores the scale
in the entity (+0x3D8), passes it to the entity's physics (its params with the scale) and marks the world
matrix dirty. Measured 2026-10-31 (24_SHANTYDAY, the Deck save, every Merc at fScale 0.77): the character
draws (vertex shader 015857D1) carry a world matrix of scale 0.77 while the bone matrices stay 1; the small
Grunts walk, aim, shoot and fall to a shotgun hit (the crosshair turns red on them). The level data sets
fScale for nobody. `entity_scale` in a character config (character_import.py) hooks OnReset: before the test it
loads, once, the carrier script of each scaled model of the config and sets fScale from `HaloScale[stem of
Properties.fileModel]`. A carrier is one of the game's AI character scripts (`scripts/ai/characters/...`, plain
definitions such as `AICharacter.Dragon = {...}`, in both games, touched by no other mod; lua_patch.CARRIERS,
one per scaled model in the order of the models' file names): the mod that replaces the model ships it with one
more line, `HaloScale[stem] = size`; without that mod the game's own carrier runs and sets nothing. Every mod
with a scaled model ships the same hooked BasicAI (no conflict in the menu), so the size follows the alternative
switched on for each FCI model. Own marker files do not work: `Script:LoadScript` of a script that is in neither
lua.dat nor the game folder stops the game with a script error (Evolution 001E053D raises it, 001E047F ->
0018F920; the error screen drawn over the frame, the game at 4 frames a second in the menu), and Lua's protected
`call` does not catch it; neither `GetBonePos` (nothing posed yet at OnReset) nor `GetLocalBBox` (not the model's
header box) can tell the models apart. Grunt: 0.77 (1.82 m drawn at 1.40 m). Checked in game 2026-10-31 (the
Deck save in 24_SHANTYDAY): the kit 3 Grunt mod next to the kit 1 Elite mod, the Grunts smaller than the Elites
beside them, the Elites unscaled, the game at its usual speed; Instincts' 02_Native with the common-merc Grunt
runs as before.

**Results (built 2026-10-30; the earlier combined Elite mod worked in Evolution).** Software
renders of every built model in the bind pose and four poses driven by the template's bones (a stride with
the arms down, forearms across the belly, a crouch with the head turned and the hands twisted) next to the
original (fci-modsrc `mods\_check\<game>\char-<model>.png`): no tears, soles within 1 cm of the
template's floor in the bind pose, textures in place through the redirected materials. Every rebuilt model
keeps its template's version, bones, parts and physics tail; between all mod folders only the alternatives
for one model share files. Heights: elite 1.94 m (spec-ops 2.03), Jackal 2.00, Grunt 1.82 (drawn at 0.77: 1.40), Flood 1.82,
Hunter 2.80. The Instincts models and the Trigen hold +-1 m around the pelvis at 1/32767 and get 2/32767 when
the creature is taller (Elite, Jackal); the pirates', rebels' and feral warriors' own 0.002 holds +-65 m.
Hit capsules and ragdoll stay the template's (human, or the Chucker's).

## Open

- In the game: the position scale doubled (2/32767), textures larger than the originals (1024 x 512 for a
  256 x 256), the hidden parts and hats, how far the Elite's crest and shoulder pads clip in the mercs'
  poses and where the weapons sit in its hands (Prop nodes, not the hand bone).
- Hit capsules and ragdoll stay human: the crest above the head capsule cannot be hit.
- The elite's neck is squashed to the Biped's 9 cm; a longer neck needs the template's Head bone moved
  (bone position and the skin matrices below it), which only works if the animations never set it.
- The physics objects' layout (capsule sizes and frames), needed if a model outgrows human proportions.
- What the colour of 32-byte vertices selects (shader 4507): almost always exactly one of r, g, b, a at
  255.
- The `.man` key format; whether the animations ever set body bone positions.
- Rebuilt characters are checked offline (all 80 skinned models re-encode to the same bind-pose and posed
  geometry); none has been loaded in the game yet, in particular one whose submesh table grew.
