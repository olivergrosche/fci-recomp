# Menus

Images: both games' default.xbe. Found 2026-10-30 from the menus' names in `.rdata` and their references,
the string tables and the menu package in `common.dat` (tools/dat2.py), and runs of tools/game_driver.py.
The main menu's MODS entry (src/fci_mainmenu.c) is built on it.

## Packages, areas, elements

The menus are Ubisoft's Magma UI. A package (`Magma\CryPreGame.mgb` in `common.dat`: the title, main menu,
multiplayer, special features and credits pages) holds areas (`P_Start`, `P_Main`, ...) and their elements
(buttons `B_*`, texts `T_*`). Areas, elements and string-table keys are known by the CRC-32 of their name
(zlib's, the case as written: `B_StoryMode` is 17130B2F): Instincts 003529B0, Evolution 0026ACB2.

- An area: its elements' pointers at +8..+0xC. Lookup by name: Instincts 000665A0 (ecx = name, eax = area),
  Evolution 0004F7FC (ecx = name; the area on the stack, 0026A628 searches).
- An element (a button, vtable Instincts 00623CD4): +4 its id; +8 its view (the label, its wide text at
  view+0x40); +0x18 bit 0 shown; +0x1C and +0x20 the ids of the elements above and below (the menu's up/down,
  a ring; a hidden element is passed over); +0x4C bit 1 selectable (bits 0x14 with it: the focus).
- Hiding a button: +0x18 bit 0 cleared, then the selectable bit, and the area's vtable +0x48 told about the
  element. Evolution has the second half as a function, 00270FEC (edx = element, al = on); Instincts inlines
  it (0014E6F0).
- The package keeps each button's states as int16 x, y on the 640x480 screen and two 1.0 scale floats
  (records with vtable 00624390 at run time). `P_Main`'s buttons:

| Button | Instincts | Evolution |
|---|---|---|
| `B_StoryMode` | 62, 140 | 48, 114 |
| `B_Tutorial` | - | 48, 144 |
| `B_Multiplayer` | 62, 175 | 48, 174 |
| `B_MapEditor` | 62, 210 | 48, 204 |
| `B_Options` | 62, 245 | 48, 234 |
| `B_SpecialFeatures` | 62, 280 | 48, 324, hidden |
| `B_Credits` | 62, 315 | 48, 264 |
| `B_Cheats` | 62, 350 | 48, 294 |
| `B_CheatsDebug` | 70, 380, hidden | 64, 354, hidden |

Evolution's designers moved Special Features below CHEATS MENU, on the menu's grid, and hid it.

## Strings

Labels and help lines are XML string tables, `LANGUAGES\<language>\<file>` in `common.dat` (`english`
UTF-8, `french`, `german`, `italian`, `spanish` UTF-16; `g_language` chooses). The main menu page's file is
`PreGameMenu.xml`: `<section name="P_Main">` the buttons' labels by element name, `<section
name="HelpText">` the line under the menu. A table is loaded per file and language (Instincts 00072980,
Evolution 000579A3) into maps keyed by the CRC-32 of file, section and entry; the language object starts with
its name (a std::string).

The lookup builds a std::wstring (the text in place up to 7 characters, capacity at +0x18):

- Instincts 00072570: ecx = file, edx = language, esi = the string; section, entry on the stack; ret 8.
  Not found: a placeholder through 00044FC0 (ecx = string, eax = text; the length; ret 4), the game's assign.
- Evolution 000577C3, stdcall: language, string, section, entry, file; ret 0x14. Not found: the placeholder
  through 00037AB8 (stdcall: string, text; ret 8).

Callers: a page's localize step (Instincts 00109170, vtable +0x6C) looks up every button and text of an area
by (the page's file, the area, the element); the page's focus handler (vtable slot 0: Instincts 0014EE40,
Evolution 000FC70F) the focused element's `HelpText` line.

`common.dat` also holds a `UBISTRINGTABLE` export (`MAGMA_PACKAGE_NAME`, `MAGMA_AREA_ID`,
`MAGMA_ELEMENT_ID` with the same CRC-32s), the menu editor's view of the texts.

## The main menu page

Instincts: vtable 00609150, constructor 0014DA50. Evolution: vtable 004BEC78, constructor 000FA3A8. The
constructor names the package and the areas in order, which are the area numbers: 0 `P_Start`, 1 `P_Main`,
2 `P_Multiplayer`, 3 `P_Attract`, 4 `P_SpecialFeatures`, 5 `P_Credits` (the areas' list at page+0x4C).
Evolution's hides `B_SpecialFeatures` there (000FA51E).

| Slot | Instincts | Evolution | |
|---|---|---|---|
| 0 | 0014EE40 | 000FC70F | focus: the `HelpText` line of the focused element |
| 2 (+8) | 0014EFF0 | 000FB0A2 | press: the dispatch below |
| 7 (+0x1C) | 0014E8D0 | 000FAC7B | start: a chain of steps (Instincts 0014E190, Evolution 000FA783), the last hides `B_CheatsDebug` (0014E6F0, 000FAA54: eax = page; ret, eax = 1) |
| +0x2C | 00108340 | 000CEF2A | turn to area (number, 1, 1) |

### Press dispatch

Slot 2, thiscall (page; event), ret 4, returns al = 0. The event's +4 is the pressed element's id; the
handler compares it with each name's CRC-32 in turn and acts on the first match:

| Element | Instincts 0014EFF0 | Evolution 000FB0A2 |
|---|---|---|
| `B_StoryMode` | the story page [006B324C] +0x24, or first the profiles page ([006B3258] +0x70) | [0056ADC4], the profiles [0056ADD4] |
| `B_Tutorial` | - | 000FCB1B, after the same profile check |
| `B_SplitScreen` | [006B3254] +0x24 | 000FBF53 |
| `B_Multiplayer` | area 2, or first the profiles page | 000FC031 |
| `B_MapEditor` | 0014F880 (the editor's relaunch) | 000FB742 |
| `B_SystemLink` | [006B341C] +0x24 | 000FBF7E |
| `B_Options` | the profiles page ([006B3258] +0x70) | [0056ADD4] +0x74 |
| `B_Live` | 00176830 | 000FBFA2 |
| `B_Cheats` | the cheats page (made once by 00146410, kept at page+0x9C) +0x24 | the same through 000F63DB |
| `B_SpecialFeatures` | area 4 | area 4 |
| `B_Credits` | area 5 | area 5 |
| in area 4 | 0014F310: `B_Feature1`, `B_Feature2` (videos) | 000FB2FF |
| `B_MapManager` | - | [0056ADE0] +0x74 |

`B_CheatsDebug` has no case in either: its press does nothing.

## The MODS entry (src/fci_mainmenu.c)

A hidden button of `P_Main` is shown as MODS; its press opens the mod menu (src/xbr/fci_overlay.cpp), and
closing that leaves the main menu as it was. Nothing in the game's files changes.

- Instincts: `B_CheatsDebug`, below CHEATS MENU. A gate on the start step 0014E6F0 keeps it shown; a prehook
  on the press handler sees its id. Up from STORY MODE reaches it (the ring).
- Evolution: `B_SpecialFeatures`, below CHEATS MENU on the grid (`B_CheatsDebug` sits a row lower and
  indented). A gate on the start step 000FAA54 shows it again (+0x18 bit 0, then 00270FEC with al = 1) and
  lets the step hide `B_CheatsDebug` as before; a gate on the press handler opens the mod menu in place of
  area 4, which Evolution leaves empty.
- Label and help line: gates on the lookups answer for (PreGameMenu.xml, `P_Main` or `HelpText`, the entry's
  button) with MODS and a line in the table's language, built by the game's own string functions (00044FC0,
  00037AB8 from host code via recomp_lookup), so the game frees them as its own.

Checks (2026-10-30, test installs, tools/game_driver.py):

- Instincts and Evolution: MODS under CHEATS MENU with its help line; the pad's Up from STORY MODE selects
  it, A opens the mod menu (`[FCI] mod menu opened (the main menu's MODS)`) without switching a mod, B closes
  it, and the main menu goes on (Down to STORY MODE).
- The keyboard (`RECOMP_KEYBOARD=1`, as a player's launch): Up, Enter or Space open it, Escape closes it.
  F1, Insert and both sticks still open and close it (both games, at the main menu).
- Evolution: OPTIONS and back keep MODS; French and German (`RECOMP_CVAR_g_language`) show their lines.
- No mods: the entry is there and the menu says it found none.

Open:

- Instincts' entry sits where the layout put `B_CheatsDebug`, 8 units right of the column and 30 below
  CHEATS MENU instead of 35: a row on the grid would leave the menu's panel. The label's own state record
  (view+0x08, x and y 0) does not place it; the records that do (00624390, 0x20 apart) were found in memory
  but not their owner.
- The mouse: its motion is the right stick, which moves the menus' selection; its buttons are the triggers
  (MOUSE1 = RT), which no menu entry takes. Pressing an entry takes A (Enter, Space) or a controller.
