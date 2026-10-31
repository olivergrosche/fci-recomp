/* Mods: folders of replacement files for the game's archives, switched on in the mod menu (xbr/fci_overlay.cpp).
 *
 *   <exe folder>\mods\<id>\mod.ini                name, group, description, credit (UTF-8, all optional)
 *   <exe folder>\mods\<id>\<archive>\<path>       a file in place of the archive's: weaponpack\animations\...
 *   <exe folder>\mods\<id>\particles-add\*.xml    particle effects added to every level's library (below)
 *   <exe folder>\mods\enabled.txt                 the switched-on mods, an id a line; a later one wins
 *   <exe folder>\mods\settings.ini                the menu's settings: weapon-strength, enemy-damage (percent)
 *
 * <archive> is a .dat of the game folder named without its extension (weaponpack, or
 * levels\21_DUNEA\21_dunea for a level's). An archive names its files only by the CRC-32 of the lower-case
 * path (tools/dat2.py, re/notes/ARCHIVES.md). At start, before the game opens a file, the archives the
 * enabled mods touch are merged into mods\.cache (once for each choice: the name carries a digest of the
 * inputs) and the kernel opens those instead of the game's (patches/runtime/0022). The game folder stays as
 * installed. Each instance does this anew; Evolution starts a new one at every level change and on the way
 * back to the main menu, so a choice made in the menu takes effect there.
 *
 * RECOMP_FCI_MODS_DIR names another mods folder (test runs, whose executable runs from a copy). */
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <windows.h>

#include "kernel.h"
#include "fci_mods.h"

#define MAX_MODS     256
#define MAX_ARCHIVES 128 /* every level's, when a mod adds particle effects */
#define FIELD        512
#define ADDS_DIR     L"particles-add" /* a mod's folder of particle effects for every level's library */

typedef struct {
    int archive;   /* into archives[] */
    uint32_t hash; /* the file's name in it */
    WCHAR *src;    /* the replacement */
} Replacement;

typedef struct {
    char id[128], name[FIELD], group[FIELD], description[2048], credit[FIELD];
    Replacement *files;
    int nfiles, enabled, active;
    WCHAR **adds; /* particle effects for every level's library: <mod>\particles-add\*.xml */
    int nadds;
} Mod;

typedef struct {
    WCHAR rel[MAX_PATH];      /* weaponpack, levels\21_DUNEA\21_dunea */
    WCHAR host_dat[MAX_PATH]; /* the kernel's path of the game's own .dat and .fat */
    WCHAR host_fat[MAX_PATH];
    WCHAR cache_dat[MAX_PATH]; /* the merged copies, empty when no enabled mod touches it */
    WCHAR cache_fat[MAX_PATH];
    uint32_t library;   /* the name of its particle library when the enabled mods add effects to it, else 0 */
    volatile LONG lazy; /* 1: merged when the game first opens it (it only gets particle effects) */
} Archive;

static Mod mods[MAX_MODS];
static int nmods;
static Archive archives[MAX_ARCHIVES];
static int narchives;
static WCHAR game_w[MAX_PATH], mods_w[MAX_PATH], cache_w[MAX_PATH];
static char mods_utf8[MAX_PATH * 3];

static void utf8(const WCHAR *w, char *out, int cap)
{
    if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, out, cap, NULL, NULL))
        out[0] = 0;
}

static void wide(const char *s, WCHAR *out, int cap)
{
    if (!MultiByteToWideChar(CP_UTF8, 0, s, -1, out, cap))
        out[0] = 0;
}

static int exists(const WCHAR *path)
{
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

/* ---- names ---- */

static uint32_t crc_table[256];

static uint32_t crc32_of(const char *s)
{
    uint32_t c = 0xFFFFFFFFu;
    if (!crc_table[1])
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t k = i;
            for (int b = 0; b < 8; b++)
                k = k & 1 ? 0xEDB88320u ^ (k >> 1) : k >> 1;
            crc_table[i] = k;
        }
    for (; *s; s++)
        c = crc_table[(c ^ (uint8_t)*s) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

/* the archive's name for a path inside it: lower case, backslashes, one leading backslash (tools/dat2.py) */
static uint32_t name_hash(const WCHAR *inner)
{
    char key[MAX_PATH + 2];
    int n = 0;
    key[n++] = '\\';
    for (; *inner && n < MAX_PATH; inner++) {
        WCHAR c = *inner == L'/' ? L'\\' : *inner;
        if (c > 0x7F)
            return 0; /* the games' paths are ASCII */
        key[n++] = (char)tolower((unsigned char)c);
    }
    key[n] = 0;
    return crc32_of(key);
}

/* ---- the game's archives ---- */

/* the archive named part (weaponpack, levels\02_Native\02_Native): its index, registered on first use; -1
 * when the game folder has no such .dat */
static int archive_named(const WCHAR *part)
{
    WCHAR dat[MAX_PATH];
    for (int i = 0; i < narchives; i++)
        if (!_wcsicmp(archives[i].rel, part))
            return i;
    swprintf_s(dat, MAX_PATH, L"%s\\%s.dat", game_w, part);
    if (exists(dat) && narchives < MAX_ARCHIVES) {
        Archive *a = &archives[narchives];
        char guest[MAX_PATH * 3], u[MAX_PATH * 3];
        wcscpy_s(a->rel, MAX_PATH, part);
        utf8(part, u, sizeof u);
        snprintf(guest, sizeof guest, "D:\\%s.dat", u);
        xbox_translate_path(guest, a->host_dat, MAX_PATH);
        snprintf(guest, sizeof guest, "D:\\%s.fat", u);
        xbox_translate_path(guest, a->host_fat, MAX_PATH);
        return narchives++;
    }
    return -1;
}

/* the archive a mod's file belongs to: the shortest leading part of its path that names a .dat in the game
 * folder; -1 when none does (a readme, say) */
static int archive_of(const WCHAR *rel, const WCHAR **inner)
{
    WCHAR part[MAX_PATH];
    for (const WCHAR *p = rel; (p = wcschr(p, L'\\')) != NULL; p++) {
        size_t n = (size_t)(p - rel);
        int a;
        if (n >= MAX_PATH)
            return -1;
        wmemcpy(part, rel, n);
        part[n] = 0;
        if ((a = archive_named(part)) >= 0) {
            *inner = p + 1;
            return a;
        }
    }
    return -1;
}

/* a level's archive (levels\<dir>\<name>) holds the level's particle library as
 * levels\<dir>\<dir>_DepLoadParticles.xml (re/notes/BLOOD.md); 0 for the other archives */
static uint32_t library_of(const WCHAR *rel)
{
    WCHAR inner[MAX_PATH];
    const WCHAR *dir = rel + 7, *end;
    if (_wcsnicmp(rel, L"levels\\", 7) || !(end = wcschr(dir, L'\\')) || end == dir || wcschr(end + 1, L'\\'))
        return 0;
    swprintf_s(inner, MAX_PATH, L"levels\\%.*s\\%.*s_DepLoadParticles.xml", (int)(end - dir), dir,
               (int)(end - dir), dir);
    return name_hash(inner);
}

/* ---- the mods ---- */

static void ini_value(Mod *m, const char *key, const char *value)
{
    char *to = !_stricmp(key, "name")          ? m->name
               : !_stricmp(key, "group")       ? m->group
               : !_stricmp(key, "description") ? m->description
               : !_stricmp(key, "credit")      ? m->credit
                                               : NULL;
    size_t cap = to == m->description ? sizeof m->description : FIELD;
    if (to)
        snprintf(to, cap, "%s", value);
}

static void read_ini(Mod *m, const WCHAR *path)
{
    char line[2048];
    FILE *f = _wfopen(path, L"rb");
    if (!f)
        return;
    while (fgets(line, sizeof line, f)) {
        char *k = line, *v, *e;
        if (!strncmp(k, "\xEF\xBB\xBF", 3)) /* a BOM */
            k += 3;
        while (*k == ' ' || *k == '\t')
            k++;
        if (*k == ';' || *k == '#' || !(v = strchr(k, '=')))
            continue;
        for (e = v; e > k && (e[-1] == ' ' || e[-1] == '\t'); e--)
            ;
        *e = 0;
        for (v++; *v == ' ' || *v == '\t'; v++)
            ;
        for (e = v + strlen(v); e > v && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' '); e--)
            ;
        *e = 0;
        ini_value(m, k, v);
    }
    fclose(f);
}

static void add_files(Mod *m, const WCHAR *root, const WCHAR *rel)
{
    WCHAR pattern[MAX_PATH], path[MAX_PATH];
    WIN32_FIND_DATAW fd;
    HANDLE h;
    swprintf_s(pattern, MAX_PATH, L"%s%s%s\\*", root, *rel ? L"\\" : L"", rel);
    if ((h = FindFirstFileW(pattern, &fd)) == INVALID_HANDLE_VALUE)
        return;
    do {
        WCHAR sub[MAX_PATH];
        const WCHAR *inner;
        int a;
        if (fd.cFileName[0] == L'.')
            continue;
        swprintf_s(sub, MAX_PATH, L"%s%s%s", rel, *rel ? L"\\" : L"", fd.cFileName);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            add_files(m, root, sub);
            continue;
        }
        if (!_wcsnicmp(sub, ADDS_DIR L"\\", wcslen(ADDS_DIR) + 1) && wcslen(sub) > 4
            && !_wcsicmp(sub + wcslen(sub) - 4, L".xml")) { /* effects for the levels' particle libraries */
            swprintf_s(path, MAX_PATH, L"%s\\%s", root, sub);
            m->adds = realloc(m->adds, sizeof(WCHAR *) * (m->nadds + 1));
            m->adds[m->nadds++] = _wcsdup(path);
            continue;
        }
        if ((a = archive_of(sub, &inner)) < 0)
            continue;
        swprintf_s(path, MAX_PATH, L"%s\\%s", root, sub);
        m->files = realloc(m->files, sizeof(Replacement) * (m->nfiles + 1));
        m->files[m->nfiles].archive = a;
        m->files[m->nfiles].hash = name_hash(inner);
        m->files[m->nfiles].src = _wcsdup(path);
        m->nfiles++;
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

static void scan(void)
{
    WCHAR pattern[MAX_PATH];
    WIN32_FIND_DATAW fd;
    HANDLE h;
    swprintf_s(pattern, MAX_PATH, L"%s\\*", mods_w);
    if ((h = FindFirstFileW(pattern, &fd)) == INVALID_HANDLE_VALUE)
        return;
    do {
        WCHAR root[MAX_PATH], ini[MAX_PATH];
        Mod *m;
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || fd.cFileName[0] == L'.' || nmods >= MAX_MODS)
            continue;
        m = &mods[nmods];
        memset(m, 0, sizeof *m);
        utf8(fd.cFileName, m->id, sizeof m->id);
        snprintf(m->name, FIELD, "%s", m->id);
        swprintf_s(root, MAX_PATH, L"%s\\%s", mods_w, fd.cFileName);
        swprintf_s(ini, MAX_PATH, L"%s\\mod.ini", root);
        read_ini(m, ini);
        add_files(m, root, L"");
        if (m->nfiles || m->nadds)
            nmods++;
        else
            fprintf(stderr, "[FCI] mods: %s replaces no file of the game; left out\n", m->id);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

/* ---- the choice ---- */

static int order[MAX_MODS], norder; /* the enabled mods, in the file's order */

static void load_choice(void)
{
    WCHAR path[MAX_PATH];
    char line[256];
    FILE *f;
    norder = 0;
    swprintf_s(path, MAX_PATH, L"%s\\enabled.txt", mods_w);
    if (!(f = _wfopen(path, L"rb")))
        return;
    while (fgets(line, sizeof line, f)) {
        char *e = line + strlen(line);
        char *s = line;
        if (!strncmp(s, "\xEF\xBB\xBF", 3))
            s += 3;
        while (e > s && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' '))
            *--e = 0;
        for (int i = 0; i < nmods; i++)
            if (!_stricmp(mods[i].id, s) && !mods[i].enabled) {
                mods[i].enabled = 1;
                order[norder++] = i;
            }
    }
    fclose(f);
}

static void save_choice(void)
{
    WCHAR path[MAX_PATH], tmp[MAX_PATH];
    FILE *f;
    swprintf_s(path, MAX_PATH, L"%s\\enabled.txt", mods_w);
    swprintf_s(tmp, MAX_PATH, L"%s\\enabled.txt.new", mods_w);
    if (!(f = _wfopen(tmp, L"wb"))) {
        fprintf(stderr, "[FCI] mods: cannot write %S\n", tmp);
        return;
    }
    fputs("# the mods the mod menu (F1) switched on, a folder name a line; a later one wins\r\n", f);
    for (int k = 0; k < norder; k++)
        fprintf(f, "%s\r\n", mods[order[k]].id);
    fclose(f);
    MoveFileExW(tmp, path, MOVEFILE_REPLACE_EXISTING);
}

/* ---- the settings ---- */

static volatile LONG weapon_strength = 100, enemy_damage = 100; /* percent; the menu sets, the game reads */

static int strength_value(int percent)
{
    percent = (percent + FCI_STRENGTH_STEP / 2) / FCI_STRENGTH_STEP * FCI_STRENGTH_STEP;
    return percent < FCI_STRENGTH_MIN   ? FCI_STRENGTH_MIN
           : percent > FCI_STRENGTH_MAX ? FCI_STRENGTH_MAX
                                        : percent;
}

static void load_settings(void)
{
    WCHAR path[MAX_PATH];
    char line[256];
    FILE *f;
    swprintf_s(path, MAX_PATH, L"%s\\settings.ini", mods_w);
    if (!(f = _wfopen(path, L"rb")))
        return;
    while (fgets(line, sizeof line, f)) {
        char key[64];
        int value;
        if (sscanf(line, " %63[a-z-] = %d", key, &value) != 2)
            continue;
        if (!strcmp(key, "weapon-strength"))
            weapon_strength = strength_value(value);
        else if (!strcmp(key, "enemy-damage"))
            enemy_damage = strength_value(value);
    }
    fclose(f);
    fprintf(stderr, "[FCI] settings: weapon strength %ld %%, enemy damage %ld %%\n", weapon_strength,
            enemy_damage);
}

static void save_settings(void)
{
    WCHAR path[MAX_PATH], tmp[MAX_PATH];
    FILE *f;
    CreateDirectoryW(mods_w, NULL);
    swprintf_s(path, MAX_PATH, L"%s\\settings.ini", mods_w);
    swprintf_s(tmp, MAX_PATH, L"%s\\settings.ini.new", mods_w);
    if (!(f = _wfopen(tmp, L"wb"))) {
        fprintf(stderr, "[FCI] settings: cannot write %S\n", tmp);
        return;
    }
    fputs("; the mod menu's settings (F1), in percent of the game's own\r\n", f);
    fprintf(f,
            "; the damage Jack's weapons deal to characters: bullets, melee, his explosions\r\n"
            "weapon-strength = %ld\r\n",
            weapon_strength);
    fprintf(f, "; the damage others deal to Jack\r\nenemy-damage = %ld\r\n", enemy_damage);
    fclose(f);
    MoveFileExW(tmp, path, MOVEFILE_REPLACE_EXISTING);
}

int fci_mods_weapon_strength(void) { return weapon_strength; }
int fci_mods_enemy_damage(void) { return enemy_damage; }

void fci_mods_set_strengths(int weapon, int enemy)
{
    weapon = strength_value(weapon);
    enemy = strength_value(enemy);
    if (weapon == weapon_strength && enemy == enemy_damage)
        return;
    InterlockedExchange(&weapon_strength, weapon);
    InterlockedExchange(&enemy_damage, enemy);
    save_settings();
    fprintf(stderr, "[FCI] settings: weapon strength %d %%, enemy damage %d %%\n", weapon, enemy);
}

/* ---- merging ---- */

typedef struct {
    uint32_t offset, size, hash;
    const WCHAR *src; /* a replacement, or NULL for the game's own bytes */
    uint8_t *mem;     /* or these: a particle library with the mods' effects */
    uint32_t mem_size;
} Entry;

static int by_offset(const void *a, const void *b)
{
    const Entry *x = a, *y = b;
    return x->offset < y->offset ? -1 : x->offset > y->offset;
}

static int by_hash(const void *a, const void *b)
{
    const Entry *x = a, *y = b;
    return x->hash < y->hash ? -1 : x->hash > y->hash;
}

static uint64_t fnv(uint64_t h, const void *p, size_t n)
{
    const uint8_t *b = p;
    while (n--)
        h = (h ^ *b++) * 0x100000001B3ull;
    return h;
}

static uint64_t file_stamp(uint64_t h, const WCHAR *path)
{
    WIN32_FILE_ATTRIBUTE_DATA d;
    if (GetFileAttributesExW(path, GetFileExInfoStandard, &d)) {
        h = fnv(h, &d.nFileSizeLow, sizeof d.nFileSizeLow);
        h = fnv(h, &d.nFileSizeHigh, sizeof d.nFileSizeHigh);
        h = fnv(h, &d.ftLastWriteTime, sizeof d.ftLastWriteTime);
    }
    return fnv(h, path, wcslen(path) * sizeof(WCHAR));
}

static int copy_range(HANDLE from, uint32_t offset, uint32_t size, HANDLE to)
{
    static uint8_t buf[1 << 16];
    LARGE_INTEGER at;
    at.QuadPart = offset;
    if (!SetFilePointerEx(from, at, NULL, FILE_BEGIN))
        return 0;
    while (size) {
        DWORD n = size < (uint32_t)sizeof buf ? size : (DWORD)sizeof buf, got, put;
        if (!ReadFile(from, buf, n, &got, NULL) || got != n || !WriteFile(to, buf, n, &put, NULL) || put != n)
            return 0;
        size -= n;
    }
    return 1;
}

static int read_all(const WCHAR *path, uint8_t **out, DWORD *size)
{
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    DWORD got;
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    *size = GetFileSize(h, NULL);
    *out = malloc(*size ? *size : 1);
    if (!ReadFile(h, *out, *size, &got, NULL) || got != *size) {
        CloseHandle(h);
        free(*out);
        return 0;
    }
    CloseHandle(h);
    return 1;
}

/* ---- particle effects for every level's library ----
 *
 * A level's effects (blood, muzzle flashes, impacts) come from its archive's particle library, an XML file of
 * <Particles Name="Lib.Effect"> elements under <ParticleLibrary>; scripts name them <group>.Lib.Effect, and a
 * level looks every name up in its own library only (re/notes/BLOOD.md). A mod's particles-add\*.xml holds
 * such elements (in a <ParticleLibrary> of its own or bare). They go into the library of every level's
 * archive the game opens, after whatever replaced it (a blood mod's), so mods that add effects and mods that
 * replace the library work together. A name the library already has stays the library's; of two mods adding
 * the same name, the later one wins. */

typedef struct {
    const char *at; /* <Particles ... </Particles> */
    size_t len;
    char name[160];
} Block;

static Block *add_blocks; /* the enabled mods' effects, a name once */
static int nadd_blocks;
static uint64_t adds_key; /* their files, for the merged copies' digest */

static const char *find_text(const char *t, const char *end, const char *s)
{
    size_t n = strlen(s);
    for (; t + n <= end; t++)
        if (!memcmp(t, s, n))
            return t;
    return NULL;
}

/* the top-level <Particles> elements of t[0..size), each with its name; their number */
static int blocks_of(const char *t, size_t size, Block **out)
{
    const char *end = t + size, *start = NULL, *p = t;
    int depth = 0, n = 0, cap = 0;
    Block *b = NULL;
    while ((p = memchr(p, '<', (size_t)(end - p))) != NULL) {
        const char *close;
        if (end - p >= 4 && !memcmp(p, "<!--", 4)) { /* a comment */
            if (!(p = find_text(p + 4, end, "-->")))
                break;
            continue;
        }
        if (!(close = memchr(p, '>', (size_t)(end - p))))
            break;
        if (end - p > 10 && !memcmp(p, "<Particles", 10) && p[10] && strchr(" \t\r\n/>", p[10])) {
            if (++depth == 1) {
                const char *name = find_text(p, close, "Name=\"");
                for (start = p; start > t && (start[-1] == ' ' || start[-1] == '\t'); start--)
                    ; /* with its line's indent */
                if (n == cap)
                    b = realloc(b, sizeof *b * (cap = cap ? cap * 2 : 64));
                b[n].name[0] = 0;
                if (name) {
                    const char *q = name + 6, *e = memchr(q, '"', (size_t)(close - q));
                    if (e && e - q < (ptrdiff_t)sizeof b[n].name) {
                        memcpy(b[n].name, q, (size_t)(e - q));
                        b[n].name[e - q] = 0;
                    }
                }
            }
            if (close[-1] == '/')
                depth--;
        } else if (end - p > 11 && !memcmp(p, "</Particles", 11) && p[11] && strchr(" \t\r\n>", p[11])) {
            depth--;
        } else {
            p = close + 1;
            continue;
        }
        if (depth < 0)
            break; /* not a library */
        if (!depth && start) {
            b[n].at = start;
            b[n++].len = (size_t)(close + 1 - start);
            start = NULL;
        }
        p = close + 1;
    }
    *out = b;
    return n;
}

/* the enabled mods' effects (load_choice first) */
static void load_additions(void)
{
    adds_key = 0xCBF29CE484222325ull;
    for (int k = 0; k < norder; k++) {
        Mod *m = &mods[order[k]];
        for (int f = 0; f < m->nadds; f++) {
            uint8_t *buf;
            DWORD size;
            Block *b;
            int n;
            if (!read_all(m->adds[f], &buf, &size)) {
                fprintf(stderr, "[FCI] mods: cannot read %S\n", m->adds[f]);
                continue;
            }
            adds_key = file_stamp(adds_key, m->adds[f]);
            n = blocks_of((const char *)buf, size, &b); /* buf stays: the blocks point into it */
            for (int i = 0; i < n; i++) {
                int j;
                if (!b[i].name[0]) {
                    fprintf(stderr, "[FCI] mods: %S: a <Particles> without a Name; left out\n", m->adds[f]);
                    continue;
                }
                for (j = 0; j < nadd_blocks && _stricmp(add_blocks[j].name, b[i].name); j++)
                    ;
                if (j < nadd_blocks)
                    fprintf(stderr, "[FCI] mods: particle effect %s of %s in place of an earlier mod's\n",
                            b[i].name, m->id);
                else
                    add_blocks = realloc(add_blocks, sizeof *add_blocks * ++nadd_blocks);
                add_blocks[j] = b[i];
            }
            free(b);
            if (!n)
                fprintf(stderr, "[FCI] mods: %S holds no <Particles>\n", m->adds[f]);
        }
    }
}

/* lib with the effects it lacks before its closing </ParticleLibrary>, in *out (malloc); 0 when not a
 * library or nothing to add */
static int splice(const WCHAR *archive, const uint8_t *lib, DWORD size, uint8_t **out, uint32_t *out_size)
{
    const char *t = (const char *)lib, *end = t + size, *at = NULL, *q;
    Block *have;
    int nhave = blocks_of(t, size, &have), added = 0, kept = 0;
    size_t total = size;
    uint8_t *o;
    for (q = t; (q = find_text(q, end, "</ParticleLibrary>")) != NULL; q++)
        at = q;
    if (!at) {
        fprintf(stderr, "[FCI] mods: the particle library of %S has no </ParticleLibrary>; nothing added\n",
                archive);
        free(have);
        return 0;
    }
    while (at > t && (at[-1] == ' ' || at[-1] == '\t')) /* the closing tag's line */
        at--;
    for (int i = 0; i < nadd_blocks; i++)
        total += add_blocks[i].len + 2;
    o = malloc(total + 2);
    memcpy(o, t, (size_t)(at - t));
    total = (size_t)(at - t);
    if (total && o[total - 1] != '\n') {
        o[total++] = '\r';
        o[total++] = '\n';
    }
    for (int i = 0; i < nadd_blocks; i++) {
        int j;
        for (j = 0; j < nhave && _stricmp(have[j].name, add_blocks[i].name); j++)
            ;
        if (j < nhave) {
            kept++;
            continue;
        }
        memcpy(o + total, add_blocks[i].at, add_blocks[i].len);
        total += add_blocks[i].len;
        o[total++] = '\r';
        o[total++] = '\n';
        added++;
    }
    memcpy(o + total, at, (size_t)(end - at));
    total += (size_t)(end - at);
    free(have);
    fprintf(stderr, "[FCI] mods: particle library of %S: %d effects added%s", archive, added,
            kept ? "" : "\n");
    if (kept)
        fprintf(stderr, ", %d it has already (its own kept)\n", kept);
    if (!added) {
        free(o);
        return 0;
    }
    *out = o;
    *out_size = (uint32_t)total;
    return 1;
}

static int read_range(const WCHAR *path, uint32_t offset, uint32_t size, uint8_t **out)
{
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    LARGE_INTEGER at;
    DWORD got = 0;
    int ok;
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    at.QuadPart = offset;
    *out = malloc(size ? size : 1);
    ok = SetFilePointerEx(h, at, NULL, FILE_BEGIN) && ReadFile(h, *out, size, &got, NULL) && got == size;
    CloseHandle(h);
    if (!ok)
        free(*out);
    return ok;
}

/* the game's archive a with the enabled mods' files written into the cache; 1 when its copies are there */
static int merge(int a)
{
    Archive *ar = &archives[a];
    WCHAR name[MAX_PATH], tmp_dat[MAX_PATH], tmp_fat[MAX_PATH];
    uint64_t key = 0xCBF29CE484222325ull;
    uint8_t *fat = NULL;
    DWORD fat_size;
    Entry *e;
    uint32_t n, total;
    HANDLE src, dst;
    int ok = 1, changed = 0;

    key = file_stamp(key, ar->host_dat);
    key = file_stamp(key, ar->host_fat);
    for (int k = 0; k < norder; k++) {
        Mod *m = &mods[order[k]];
        for (int f = 0; f < m->nfiles; f++)
            if (m->files[f].archive == a) {
                key = fnv(key, &m->files[f].hash, sizeof m->files[f].hash);
                key = file_stamp(key, m->files[f].src);
            }
    }
    if (ar->library && nadd_blocks)
        key = fnv(key, &adds_key, sizeof adds_key);
    wcscpy_s(name, MAX_PATH, ar->rel);
    for (WCHAR *p = name; *p; p++)
        if (*p == L'\\' || *p == L'/')
            *p = L'_';
    swprintf_s(ar->cache_dat, MAX_PATH, L"%s\\%s.%016llx.dat", cache_w, name, (unsigned long long)key);
    swprintf_s(ar->cache_fat, MAX_PATH, L"%s\\%s.%016llx.fat", cache_w, name, (unsigned long long)key);
    if (exists(ar->cache_dat) && exists(ar->cache_fat))
        return 1;
    { /* earlier choices' copies of this archive; one an older instance still has open stays */
        WCHAR pattern[MAX_PATH], old[MAX_PATH];
        WIN32_FIND_DATAW fd;
        HANDLE h;
        swprintf_s(pattern, MAX_PATH, L"%s\\%s.*", cache_w, name);
        if ((h = FindFirstFileW(pattern, &fd)) != INVALID_HANDLE_VALUE) {
            do {
                swprintf_s(old, MAX_PATH, L"%s\\%s", cache_w, fd.cFileName);
                DeleteFileW(old);
            } while (FindNextFileW(h, &fd));
            FindClose(h);
        }
    }

    if (!read_all(ar->host_fat, &fat, &fat_size) || fat_size < 8 || memcmp(fat, "DAT2", 4)
        || fat_size != 8 + 12 * (n = *(uint32_t *)(fat + 4))) {
        fprintf(stderr, "[FCI] mods: %S is not a DAT2 index\n", ar->host_fat);
        free(fat);
        return 0;
    }
    e = calloc(n + 4096, sizeof *e); /* room for files the archive lacks */
    for (uint32_t i = 0; i < n; i++) {
        memcpy(&e[i].offset, fat + 8 + 12 * i, 4);
        memcpy(&e[i].size, fat + 12 + 12 * i, 4);
        memcpy(&e[i].hash, fat + 16 + 12 * i, 4);
    }
    free(fat);
    total = n;
    for (int k = 0; k < norder; k++) { /* a later mod wins */
        Mod *m = &mods[order[k]];
        for (int f = 0; f < m->nfiles; f++) {
            uint32_t i;
            if (m->files[f].archive != a)
                continue;
            for (i = 0; i < total && e[i].hash != m->files[f].hash; i++)
                ;
            if (i == total) { /* a file the archive lacks: after the rest */
                if (total == n + 4096)
                    continue;
                e[total].offset = 0xFFFFFFFFu;
                e[total++].hash = m->files[f].hash;
            }
            e[i].src = m->files[f].src;
            changed++;
        }
    }
    if (ar->library && nadd_blocks) { /* the mods' particle effects into the level's library */
        uint32_t i;
        uint8_t *lib;
        DWORD size;
        for (i = 0; i < total && e[i].hash != ar->library; i++)
            ;
        if (i == total)
            fprintf(stderr, "[FCI] mods: %S has no particle library; no effects added\n", ar->rel);
        else if (e[i].src ? read_all(e[i].src, &lib, &size)
                          : (size = e[i].size, read_range(ar->host_dat, e[i].offset, e[i].size, &lib))) {
            if (splice(ar->rel, lib, size, &e[i].mem, &e[i].mem_size))
                changed++;
            free(lib);
        }
    }
    if (!changed) { /* nothing to merge: the game's own stays */
        free(e);
        return 0;
    }
    qsort(e, total, sizeof *e, by_offset);

    swprintf_s(tmp_dat, MAX_PATH, L"%s.new", ar->cache_dat);
    swprintf_s(tmp_fat, MAX_PATH, L"%s.new", ar->cache_fat);
    src = CreateFileW(ar->host_dat, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                      FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    dst = CreateFileW(tmp_dat, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (src == INVALID_HANDLE_VALUE || dst == INVALID_HANDLE_VALUE)
        ok = 0;
    {
        uint64_t at = 0;
        for (uint32_t i = 0; ok && i < total; i++) {
            uint32_t offset = (uint32_t)at;
            if (e[i].mem) {
                DWORD put;
                ok = WriteFile(dst, e[i].mem, e[i].mem_size, &put, NULL) && put == e[i].mem_size;
                e[i].size = e[i].mem_size;
            } else if (e[i].src) {
                uint8_t *b;
                DWORD size, put;
                if (!read_all(e[i].src, &b, &size)) {
                    fprintf(stderr, "[FCI] mods: cannot read %S\n", e[i].src);
                    ok = 0;
                    break;
                }
                ok = WriteFile(dst, b, size, &put, NULL) && put == size;
                free(b);
                e[i].size = size;
            } else {
                ok = copy_range(src, e[i].offset, e[i].size, dst);
            }
            e[i].offset = offset;
            at += e[i].size;
            if (at > 0xFFFFFFFFull)
                ok = 0;
        }
    }
    if (src != INVALID_HANDLE_VALUE)
        CloseHandle(src);
    if (dst != INVALID_HANDLE_VALUE)
        CloseHandle(dst);
    if (ok) {
        FILE *f = _wfopen(tmp_fat, L"wb");
        qsort(e, total, sizeof *e, by_hash);
        ok = f != NULL;
        if (f) {
            fwrite("DAT2", 1, 4, f);
            fwrite(&total, 4, 1, f);
            for (uint32_t i = 0; i < total; i++) {
                fwrite(&e[i].offset, 4, 1, f);
                fwrite(&e[i].size, 4, 1, f);
                fwrite(&e[i].hash, 4, 1, f);
            }
            ok = !ferror(f);
            fclose(f);
        }
    }
    for (uint32_t i = 0; i < total; i++)
        free(e[i].mem);
    free(e);
    ok = ok && MoveFileExW(tmp_fat, ar->cache_fat, MOVEFILE_REPLACE_EXISTING)
         && MoveFileExW(tmp_dat, ar->cache_dat, MOVEFILE_REPLACE_EXISTING);
    if (!ok) {
        fprintf(stderr, "[FCI] mods: merging %S failed; the game's own is used\n", ar->rel);
        DeleteFileW(tmp_dat);
        DeleteFileW(tmp_fat);
    }
    return ok;
}

/* ---- the kernel's hook: the merged copies in place of the game's archives ---- */

static SRWLOCK lazy_lock = SRWLOCK_INIT;

static void host_path(xbox_host_char *path, DWORD cap)
{
    for (int a = 0; a < narchives; a++) {
        Archive *ar = &archives[a];
        int dat;
        if (!ar->cache_dat[0] && !ar->lazy)
            continue;
        if (!(dat = !_wcsicmp(path, ar->host_dat)) && _wcsicmp(path, ar->host_fat))
            continue;
        if (ar->lazy) { /* a level's archive that only gets particle effects: merged on its first open */
            AcquireSRWLockExclusive(&lazy_lock);
            if (ar->lazy) {
                if (!merge(a))
                    ar->cache_dat[0] = 0;
                else
                    fprintf(stderr, "[FCI] mods: %S from %S\n", ar->rel, ar->cache_dat);
                InterlockedExchange(&ar->lazy, 0);
            }
            ReleaseSRWLockExclusive(&lazy_lock);
        }
        if (ar->cache_dat[0])
            wcscpy_s(path, cap, dat ? ar->cache_dat : ar->cache_fat);
        return;
    }
}

/* every level's archive, for the mods' particle effects */
static void add_levels(void)
{
    WCHAR pattern[MAX_PATH];
    WIN32_FIND_DATAW dir;
    HANDLE h;
    swprintf_s(pattern, MAX_PATH, L"%s\\levels\\*", game_w);
    if ((h = FindFirstFileW(pattern, &dir)) == INVALID_HANDLE_VALUE)
        return;
    do {
        WCHAR inner[MAX_PATH];
        WIN32_FIND_DATAW fd;
        HANDLE g;
        if (!(dir.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || dir.cFileName[0] == L'.')
            continue;
        swprintf_s(inner, MAX_PATH, L"%s\\levels\\%s\\*.dat", game_w, dir.cFileName);
        if ((g = FindFirstFileW(inner, &fd)) == INVALID_HANDLE_VALUE)
            continue;
        do {
            size_t n = wcslen(fd.cFileName);
            if (n > 4 && !_wcsicmp(fd.cFileName + n - 4, L".dat")) {
                swprintf_s(inner, MAX_PATH, L"levels\\%s\\%.*s", dir.cFileName, (int)(n - 4), fd.cFileName);
                archive_named(inner);
            }
        } while (FindNextFileW(g, &fd));
        FindClose(g);
    } while (FindNextFileW(h, &dir));
    FindClose(h);
}

void fci_mods_init(const char *game_dir)
{
    const char *dir = getenv("RECOMP_FCI_MODS_DIR");
    if (!MultiByteToWideChar(CP_ACP, 0, game_dir, -1, game_w, MAX_PATH))
        return;
    if (dir && *dir) {
        MultiByteToWideChar(CP_ACP, 0, dir, -1, mods_w, MAX_PATH);
    } else {
        WCHAR *slash;
        GetModuleFileNameW(NULL, mods_w, MAX_PATH);
        if ((slash = wcsrchr(mods_w, L'\\')) != NULL)
            wcscpy_s(slash, MAX_PATH - (slash - mods_w), L"\\mods");
    }
    utf8(mods_w, mods_utf8, sizeof mods_utf8);
    swprintf_s(cache_w, MAX_PATH, L"%s\\.cache", mods_w);
    load_settings(); /* with no mods too */
    scan();
    if (!nmods)
        return;
    load_choice();
    fprintf(stderr, "[FCI] mods: %d in %s, %d switched on\n", nmods, mods_utf8, norder);
    if (!norder)
        return;
    CreateDirectoryW(cache_w, NULL);
    SetFileAttributesW(cache_w, FILE_ATTRIBUTE_HIDDEN);
    load_additions();
    if (nadd_blocks) {
        add_levels();
        for (int a = 0; a < narchives; a++)
            archives[a].library = library_of(archives[a].rel);
        fprintf(stderr, "[FCI] mods: %d particle effects for every level's library\n", nadd_blocks);
    }
    for (int a = 0; a < narchives; a++) {
        int used = 0;
        for (int k = 0; k < norder && !used; k++)
            for (int f = 0; f < mods[order[k]].nfiles && !used; f++)
                used = mods[order[k]].files[f].archive == a;
        if (!used && archives[a].library)
            archives[a].lazy = 1; /* merged when the game opens it (host_path) */
        else if (used && !merge(a))
            archives[a].cache_dat[0] = 0;
        else if (used)
            fprintf(stderr, "[FCI] mods: %S from %S\n", archives[a].rel, archives[a].cache_dat);
    }
    for (int k = 0; k < norder; k++) {
        Mod *m = &mods[order[k]];
        m->active = 1;
        for (int f = 0; f < m->nfiles; f++)
            if (!archives[m->files[f].archive].cache_dat[0])
                m->active = 0;
        fprintf(stderr, "[FCI] mods: %s (%d files, %d particle files)%s\n", m->id, m->nfiles, m->nadds,
                m->active ? "" : " NOT active");
    }
    g_xbox_host_path_hook = host_path;
}

/* ---- the menu's view ---- */

int fci_mods_count(void) { return nmods; }
const char *fci_mods_id(int i) { return mods[i].id; }
const char *fci_mods_name(int i) { return mods[i].name; }
const char *fci_mods_group(int i) { return mods[i].group; }
const char *fci_mods_description(int i) { return mods[i].description; }
const char *fci_mods_credit(int i) { return mods[i].credit; }
int fci_mods_files(int i) { return mods[i].nfiles; }
int fci_mods_enabled(int i) { return mods[i].enabled; }
int fci_mods_active(int i) { return mods[i].active; }
const char *fci_mods_folder(void) { return mods_utf8; }

/* two files of the same bytes (the hooked BasicWeapon several weapon mods ship) */
static int same_bytes(const WCHAR *x, const WCHAR *y)
{
    WIN32_FILE_ATTRIBUTE_DATA a, b;
    uint8_t *p, *q;
    DWORD n, m;
    int same;
    if (!GetFileAttributesExW(x, GetFileExInfoStandard, &a)
        || !GetFileAttributesExW(y, GetFileExInfoStandard, &b) || a.nFileSizeLow != b.nFileSizeLow
        || a.nFileSizeHigh != b.nFileSizeHigh || a.nFileSizeHigh || a.nFileSizeLow > (64u << 20))
        return 0;
    if (!read_all(x, &p, &n))
        return 0;
    if (!read_all(y, &q, &m)) {
        free(p);
        return 0;
    }
    same = n == m && !memcmp(p, q, n);
    free(p);
    free(q);
    return same;
}

/* both replace a file, each with other bytes */
static int replace_same(int i, int j)
{
    for (int a = 0; a < mods[i].nfiles; a++)
        for (int b = 0; b < mods[j].nfiles; b++)
            if (mods[i].files[a].archive == mods[j].files[b].archive
                && mods[i].files[a].hash == mods[j].files[b].hash
                && !same_bytes(mods[i].files[a].src, mods[j].files[b].src))
                return 1;
    return 0;
}

/* the menu asks every frame: worked out once (the mods do not change while the game runs) */
int fci_mods_conflict(int i, int j)
{
    static unsigned char *known; /* 0 not yet, 1 no, 2 yes */
    if (i == j || i < 0 || j < 0 || i >= nmods || j >= nmods)
        return 0;
    if (!known && !(known = calloc((size_t)nmods * nmods, 1)))
        return replace_same(i, j);
    if (!known[i * nmods + j])
        known[i * nmods + j] = known[j * nmods + i] = (unsigned char)(1 + replace_same(i, j));
    return known[i * nmods + j] == 2;
}

static void drop(int i)
{
    int k, w = 0;
    mods[i].enabled = 0;
    for (k = 0; k < norder; k++)
        if (order[k] != i)
            order[w++] = order[k];
    norder = w;
}

void fci_mods_set(int i, int on)
{
    if (i < 0 || i >= nmods || !on == !mods[i].enabled)
        return;
    if (on) {
        for (int j = 0; j < nmods; j++)
            if (mods[j].enabled && fci_mods_conflict(i, j))
                drop(j);
        mods[i].enabled = 1;
        order[norder++] = i;
    } else {
        drop(i);
    }
    save_choice();
    fprintf(stderr, "[FCI] mods: %s switched %s (from the next load)\n", mods[i].id, on ? "on" : "off");
}

int fci_mods_pending(void)
{
    for (int i = 0; i < nmods; i++)
        if (!mods[i].enabled != !mods[i].active)
            return 1;
    return 0;
}
