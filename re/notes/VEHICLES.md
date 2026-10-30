# Vehicles

Found 2026-10-30 from both games' level archives, their entity lists (`<Mission ...>` XML in each level
archive) and the compiled vehicle scripts in `lua.dat`; the model format is in MODELS.md. tools/vehicle_import.py
puts a glTF vehicle (Halo CE's Warthog) in place of one.

## The land vehicles

| Game | Script class | Model (`objects_xbox\vehicles\...`) | Gun | Entities in the campaign levels |
|---|---|---|---|---|
| both | Humvee | `hummer\hummer.xbg` | M2 Browning on a ring mount | Instincts 01 (11), 02 (1), 03 (6), 10 (1), 11 (5), 13 (2); Evolution 29 (1, with the MK19) |
| Evolution | Humvee | `hummer\hummer_camo.xbg` (desert camouflage) | Browning | 21 (2), 23 (5) |
| Evolution | PickupTruck | `pickuptruck\pickuptruck.xbg`, `_cream`, `_red`, `_silver` (23 only), `_camo` (editor) | Browning on the roll cage over the cab, or the MK19 (`bUseMortar`) | 20 (1), 21 (2: `Player_Truck`, the opening), 23 (17), 26 (16), M24 (1) |
| both | Buggy (the quad) | `atv\atv.xbg`; Evolution also `atv_camo` | - | Instincts 02 (5), 03 (13), 06 (5), 13 (1); Evolution 23 (1), 26 (2), 28 (12), 29 (2) |
| Evolution | Unimog | `unimog\unimog.xbg`, `unimog_enlarged` (28) | - | 23 (one PickupTruck entity uses this model), 28 (1) |

The multiplayer and editor archives (`farcryed`, `levels\MET_Dependency`, the `M..` maps) hold `_multi`
versions (`hummer_camo_multi`, `pickuptruck_multi`, `atv_camo_multi`, `unimog_multi`) with a flat normal map.
`StaticVehicle` (`_generic_objects\vehicles\truck\truck.xbg`) is a prop. Water and air: Boat (gunboat), Zodiac,
JetSki, Hovercraft, Sampan; Gunship (UH-60), Paraglider.

A level entity names its model (`fileModel`), wreck (`fileDestroyedModel`) and gun (`fileMountedWeaponModel`,
`Animations\Weapons\Third\Browning\Browning_Third.XBG`) among its properties, so one class drives several
models. Evolution's story starts in 21_DUNEA on `Player_Truck`, a PickupTruck with `bIsRailShooterVehicle="1"`:
the AI drives along `Player_Truck_P`, Jack mans the Browning.

Each vehicle has a wreck (`*_wrecked.xbg`, `*_camo_wrecked.xbg`; vertices with a colour whose alpha marks the
burns, shader 7CC6) and Humvee debris (`hummer_wrecked_hood`, `_ceiling`, `_wheel`, `_seat`).

## Bones

The Humvee (57 bones) and the pickup (65) share their layout; X right, Y forward, Z up, metres, the ground at
Z = 0. All bones hang on the root; only the rigid parts have geometry:

| Bone | Part | |
|---|---|---|
| `hull2` (`Hull2`) | HULL2 | the body |
| `Wheel1` .. `Wheel4` | WHEEL1 .. 4 | front left, front right, rear left, rear right; the axle along the bone's X (the Humvee's bone on the wheel's inner face, the pickup's in its middle); radius 0.45 |
| `wheelN_lower`, `wheelN_upper` | - | the wheel's travel (0.15 m) |
| `turret_mesh` | TURRET_MESH | the gun's A-frame mount, stored around the origin: drawn on the `turret` bone, turning with the gun |
| `steering_mesh` | STEERING_MESH | the steering wheel (rim radius 0.188, its column along Y), drawn on `steering_pivot`; `left_hand` and `right_hand` (its children) are where the driver's hands go |
| `turret`, `turret_pivot` | - | the gunner's ring; `gun` 0.744 m ahead of `turret` and 0.128 m above it (both vehicles) |
| `gunner_sit_pos`, `gunner_eye_pos`, `driver_sit_pos`, `eye_pos`, `passengerN_sit_pos`, `passengerN_eye_pos` | - | seats and cameras (the scripts name them) |
| `driver`, `gunner`, `passengerN`, `exit_pos` | - | where people get in and out |
| `hull1`, `hullproxy2_0N_PhysBox` | - | physics (below) |
| `front_light*`, `back_light*`, `Corona_*`, `exhaust_pos`, `fire_at`, `vehicle_damage1/2` | - | lights, effects |

| | Wheelbase | Track (wheel centres) | Wheel radius / width |
|---|---|---|---|
| Humvee | 3.262 | 1.674 | 0.450 / 0.304 |
| pickup | 3.024 | 1.420 | 0.450 / 0.303 |
| quad (`atv`) | 1.271 | 0.877 | 0.303 / 0.254 |
| Unimog | 5.866 | 2.086 | 0.637 / 0.378 |

## Physics and what drives the wheels

The model's tail (MODELS.md) holds named physics objects: `WHEEL1` .. `WHEEL4` with `WHEELn_CYLINDER01_PHYSCYL`
(the wheels' cylinders), `HULLPROXY2_0n_PHYSBOX` (boxes), `HULL1`, `HULL2` (the body's collision mesh),
`TURRET_MESH`, `STEERING_MESH`. The script's `CarDef` sets masses and the hull's offsets (`hull1`, `hull2`,
`hull3`: mass, flags, zoffset, yoffset), per wheel `driving`, `axle`, `len_max` (0.3), `stiffness`,
`friction`, and the engine, gears and steering. So the wheels' places and sizes come from the model (bones and
tail cylinders), their behaviour from the script; the physics moves the wheel bones (spin, steering, travel).
Rebuilding the drawn geometry keeps both: xbg.rebuild copies the tail and the bones byte for byte.

## The mounted gun

A separate entity (`MountedWeaponVehicle`, `MountedWeaponVehicleMortar` for the MK19) is spawned and bound to
the vehicle at `GetHelperPos("gun")`; the gunner goes to `GetTurretHelperPos("turret")` (script library
3c30e1d8). Its third-person model `animations\weapons\third\browning\browning_third.xbg` is in every level
archive with a mounted gun (37 in Instincts, 35 in Evolution), one bone `B_FRAME`, facing -Y: pivot at the
origin, muzzle at Y -0.924, the spade grips at Y +0.55 to +0.65 (their middle (0, 0.62, 0.05)). The game turns
it to face the vehicle's front (the Humvee's `gun` bone carries the half turn; the scripted pickup
`objects_xbox\island_6_dune\se\se_2_2_3_pickuptruck.xbg` in 23_DUNEC has the Browning baked in that way).

The gunner looks at the third-person model: in 21_DUNEA's opening the turret shows `browning_third.xbg` from
`gunner_eye_pos` (taken out of a mod, the original shape came back with the mod's texture; 2026-10-30).
`animations\weapons\first\browning\browning_first.xbg` (weaponpack; the same frame, plus `Bullet` and
`b_Slide`) with the arms `animations\characters\carver_first\first_person_browning.xba` is not what the
turret shows (perhaps a carried Browning). In the game's frame (640 x 480) the gun is seen from 0.744 m
behind and 0.378 m above its pivot, about 83 degrees across (focal 362 px): the Browning's muzzle lands 75 px
below the crosshair, its receiver at the bottom edge; anything taller than the Browning's receiver (Z 0.18)
near the grips fills the view. The Warthog chaingun's armour plates came out black there, two-sided too,
and the textures look about twice as bright as stored.
`browning3rd_carver.xbg` (weaponpack, `B_FRAME` turned a quarter), `browning3rd_broken.xbg` (Instincts 06 in
`animations\...`, Evolution 24 in `objects_xbox\weapons\third\browning\`) and the scripted pickup draw from the
same `animations\weapons\third\browning\browning.xbt` (weaponpack): replacing that texture means replacing all
of them. The MK19 on vehicles is `animations\weapons\third\mk19\mk19_3rd.xbg` (levels) with
`objects_xbox\weapons\third\mk19\mk19_3rd_df.xbt` (weaponpack), shared with `mk19_carver_3rd.xbg`.

## Shared textures

Wrecks and debris draw from the vehicle's own diffuse texture (`hummer_df`, `hummer_camo`, `pickuptruck_df`
...), the normal maps are shared further (`hummer_nt` also by a bloody Humvee in Instincts' 03_River,
`pickuptruck_nt` by all pickups and `se_2_2_3`), the wheel textures by the debris wheel. A new vehicle in the
vehicle's texture means rebuilding its wrecks and debris too, and leaving the wheel textures alone.

## Importing a glTF vehicle (tools/vehicle_import.py)

The template is the game's vehicle; its bones, tail and materials stay. Per part, a bone gets triangles of the
glTF (by node name or box) placed one of three ways: the body fit (the source's tire centres' middle on the
template's wheels' middle, scaled by the wheelbase, optionally narrower across), a wheel fit (a tire's centre
on the template wheel's, scaled to its radius; hubs move along) or an anchor (a source point on a target in
the bone's frame, at a given scale and turn: turret, steering wheel, the gun). All of a model's geometry goes
into one material (the wheel submeshes are pointed at the body's, same shader), whose diffuse texture gets an
atlas of the source's materials and its bump texture a flat normal map. Models are written only into the
archives that hold one of the config's vehicles. Checked offline (fci-modsrc `halo/vehicles/check.py`): the
built tires' centres lie on the template's to 0.0 mm, their radius within 0.5 mm.

The Warthog (Halo CE `vehicles\warthog\warthog`, b30): tires 0.200 units in radius, wheelbase 1.30, track 0.776;
on the Humvee 2.51 m per unit (0.93 of it across), on the pickup 2.33 (0.9 across); the tires scaled to 0.45 m
(2.25 m per unit, a little smaller than the body's). Its gun mount on `turret_mesh` and the chaingun on the
Browning's frame meet where the chaingun's pitch axis is (0, 0.596, -0.065) from `turret` (the gun's barrels on the
Browning's muzzle, as the gunner's view needs).

## Open

- Not loaded in the game yet: whether `turret_mesh` is drawn on `turret` (assumed from its shape) and turns with
  the gun, and where the first-person Browning is drawn.
- The seats stay the template's: the Humvee's gunner stands 0.57 m below the Warthog's deck between the seat
  backs (legs in the body), the pickup's gunner 0.15 m below its bed; the pickup's driver sits 0.14 m above
  the Warthog's seat. `helpers` can move helper bones, untested.
- The collision mesh stays the Humvee's (or the pickup's): bullets hit its shape, not the Warthog's.
