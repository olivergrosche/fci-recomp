/* The main menu's MODS entry (re/notes/MENUS.md). The main menu (CryPreGame's area P_Main) holds buttons the
 * game hides when the page starts, each at its own place in the layout: the entry shows one of them,
 * labelled MODS with a help line of its own, and its press opens the mod menu (xbr/fci_overlay.cpp).
 *
 *   Instincts: B_CheatsDebug ("CHEATS (DEBUG)"), below CHEATS MENU. The page's start (0014E6F0) hides it:
 *     skipped. The press handler (0014EFF0) has no case for it: the prehook opens the mod menu.
 *   Evolution: B_SpecialFeatures, which the layout moved below CHEATS MENU on the menu's grid. The page's
 *     constructor hides it; the page's start (000FAA54, where B_CheatsDebug is hidden as in Instincts) shows
 *     it again. The press handler (000FB0A2) would turn to the empty Special Features area: the gate opens
 *     the mod menu instead.
 *
 * The label and help line come from the string tables' lookup (Instincts 00072570, Evolution 000577C3): for
 * that button it answers with our texts. The game's files stay as they are. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <windows.h>

#include "re_symbols.h"
#include "recomp_types.h"

extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t alignment);
void fci_overlay_open_from_menu(void); /* xbr/fci_overlay.cpp */

/* the button's label, and its help line in the game's languages (the language's folder name) */
static const wchar_t LABEL[] = L"MODS";
static const struct {
    const char *language;
    const wchar_t *help;
} HELP[] = {
        {"english", L"Switch mods on and off. A choice takes effect when the next level loads."},
        {"french",
         L"Activez ou d\u00e9sactivez des mods. Un choix prend effet au prochain chargement d'un niveau."},
        {"german", L"Schalten Sie Mods ein und aus. Eine Wahl gilt ab dem n\u00e4chsten Laden eines Levels."},
        {"italian",
         L"Attiva o disattiva le mod. Una scelta ha effetto al prossimo caricamento di un livello."},
        {"spanish", L"Activa o desactiva mods. Un cambio se aplica al cargar el siguiente nivel."},
};
#define LANGUAGES (sizeof HELP / sizeof HELP[0])

/* names as the game keys them: the CRC-32 of the name (Instincts 003529B0, Evolution 0026ACB2) */
static uint32_t crc32_of(const char *s)
{
    uint32_t c = 0xFFFFFFFFu;
    for (; *s; s++) {
        c ^= (uint8_t)*s;
        for (int b = 0; b < 8; b++)
            c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
    }
    return ~c;
}

static uint32_t id_file, id_main, id_help, id_debug, id_special;

static void ids(void)
{
    if (id_special)
        return;
    id_file = crc32_of("PreGameMenu.xml"); /* the main menu page's string table (LANGUAGES/<language>/...) */
    id_main = crc32_of("P_Main");          /* the section of the main menu's labels */
    id_help = crc32_of("HelpText");        /* the section of the line under the menu */
    id_debug = crc32_of("B_CheatsDebug");  /* Instincts' entry */
    id_special = crc32_of("B_SpecialFeatures"); /* Evolution's */
}

/* the language object's name (a std::string at +0: its text in place under 16 bytes, else at [+4]) */
static int language_of(uint32_t language)
{
    char name[16];
    uint32_t size, text;
    if (!language)
        return 0;
    size = MEM32(language + 0x14);
    text = MEM32(language + 0x18) >= 16 ? MEM32(language + 4) : language + 4;
    if (size >= sizeof name || !text)
        return 0;
    for (uint32_t i = 0; i < size; i++)
        name[i] = (char)MEM8(text + i);
    name[size] = 0;
    for (int i = 0; i < (int)LANGUAGES; i++)
        if (!_stricmp(name, HELP[i].language))
            return i;
    return 0;
}

/* a text in guest memory, made once (the game copies it into its own string) */
static uint32_t guest_text(const wchar_t *text, uint32_t *len)
{
    static struct {
        const wchar_t *text;
        uint32_t va;
    } made[LANGUAGES + 1];
    size_t n = wcslen(text);
    int i;
    *len = (uint32_t)n;
    for (i = 0; i < (int)(LANGUAGES + 1) && made[i].text && made[i].text != text; i++)
        ;
    if (i == (int)(LANGUAGES + 1))
        return 0;
    if (!made[i].text) {
        uint32_t va = xbox_HeapAlloc((uint32_t)(n + 1) * 2, 4);
        if (!va)
            return 0;
        for (size_t k = 0; k <= n; k++)
            MEM16(va + 2 * k) = (uint16_t)text[k];
        made[i].va = va;
        made[i].text = text;
    }
    return made[i].va;
}

/* the text the lookup gives for (file, section, entry) instead of the table's, or NULL; button is the
 * title's entry */
static const wchar_t *ours(uint32_t file, uint32_t section, uint32_t entry, uint32_t language,
                           uint32_t button)
{
    static LONG logged;
    const wchar_t *text = NULL;
    if (file != id_file || entry != button)
        return NULL;
    if (section == id_main)
        text = LABEL;
    else if (section == id_help)
        text = HELP[language_of(language)].help;
    if (text && InterlockedCompareExchange(&logged, 1, 0) == 0)
        fprintf(stderr, "[FCI] main menu: MODS entry (%s)\n", HELP[language_of(language)].language);
    return text;
}

/* ---- Instincts ---- */

/* the page's start hides B_CheatsDebug (eax = page; ret, eax = 1): kept */
int fci_gate_0014E6F0(void)
{
    g_eax = 1;  /* done */
    g_esp += 4; /* ret */
    return 1;
}

/* the lookup: ecx = file, edx = language, esi = the wide string it builds; [esp+4] section, [esp+8] entry;
 * returns eax = esi, ret 8 */
int fci_gate_00072570(void)
{
    const wchar_t *text;
    recomp_func_t assign = recomp_lookup(RE_GAME_WSTRING_ASSIGN);
    uint32_t out = g_esi, src, len;
    ids();
    text = ours(g_ecx, MEM32(g_esp + 4), MEM32(g_esp + 8), g_edx, id_debug);
    if (!text || !assign || !(src = guest_text(text, &len)))
        return 0;
    /* an empty std::wstring (its text in place, room for 7), then the game's assign (00044FC0: ecx = string,
     * eax = text; the length; ret 4), as the lookup's own not-found path does */
    MEM32(out + 0x18) = 7;
    MEM32(out + 0x14) = 0;
    MEM16(out + 4) = 0;
    PUSH32(g_esp, len);
    PUSH32(g_esp, 0); /* the return address: the callee's ret pops it and the length */
    g_ecx = out;
    g_eax = src;
    assign();
    g_eax = out;
    g_esp += 12; /* ret 8 */
    return 1;
}

/* the page's press handler (thiscall; [esp+4] = event, its +4 the element): it has no case for B_CheatsDebug
 * and goes on to find none */
void fci_prehook_0014EFF0(void)
{
    uint32_t event = MEM32(g_esp + 4);
    ids();
    if (event && MEM32(event + 4) == id_debug)
        fci_overlay_open_from_menu();
}

/* ---- Evolution ---- */

/* an area's element by id: the elements' vector at +8..+0xC, an element's id at +4 (0026A628) */
static uint32_t element(uint32_t area, uint32_t id)
{
    for (uint32_t at = area ? MEM32(area + 8) : 0; at && at < MEM32(area + 0xC); at += 4)
        if (MEM32(at) && MEM32(MEM32(at) + 4) == id)
            return MEM32(at);
    return 0;
}

/* the page's start, the step that hides B_CheatsDebug (eax = page, its +0x4C the areas, P_Main second): first
 * B_SpecialFeatures, which the constructor hid, is shown and made selectable again (00270FEC: edx = element,
 * al = on; it tells the area), then the step runs */
int fci_gate_000FAA54(void)
{
    uint32_t page = g_eax, ecx = g_ecx, edx = g_edx, e;
    recomp_func_t selectable = recomp_lookup(0x00270FEC);
    ids();
    e = element(page ? MEM32(MEM32(page + 0x4C) + 4) : 0, id_special);
    if (!e || !selectable)
        return 0;
    MEM8(e + 0x18) |= 1; /* shown */
    g_edx = e;
    g_eax = 1;
    PUSH32(g_esp, 0); /* the return address, which its ret pops */
    selectable();
    g_eax = page;
    g_ecx = ecx;
    g_edx = edx;
    return 0;
}

/* the lookup, stdcall: language, the wide string it builds, section, entry, file; returns eax = the string,
 * ret 0x14 */
int fci_gate_000577C3(void)
{
    const wchar_t *text;
    recomp_func_t construct = recomp_lookup(0x00037AB8);
    uint32_t out = MEM32(g_esp + 8), src, len;
    ids();
    text = ours(MEM32(g_esp + 0x14), MEM32(g_esp + 0xC), MEM32(g_esp + 0x10), MEM32(g_esp + 4), id_special);
    if (!text || !construct || !(src = guest_text(text, &len)))
        return 0;
    /* the game's string from a text (00037AB8, stdcall: string, text; ret 8), as the lookup's not-found path */
    PUSH32(g_esp, src);
    PUSH32(g_esp, out);
    PUSH32(g_esp, 0); /* the return address: the callee's ret pops it and both arguments */
    construct();
    g_eax = out;
    g_esp += 0x18; /* ret 0x14 */
    return 1;
}

/* the page's press handler (thiscall; [esp+4] = event, its +4 the element; returns al = 0, ret 4): for
 * B_SpecialFeatures the mod menu instead of the Special Features area */
int fci_gate_000FB0A2(void)
{
    uint32_t event = MEM32(g_esp + 4);
    ids();
    if (!event || MEM32(event + 4) != id_special)
        return 0;
    fci_overlay_open_from_menu();
    g_eax &= 0xFFFFFF00u;
    g_esp += 8; /* ret 4 */
    return 1;
}
