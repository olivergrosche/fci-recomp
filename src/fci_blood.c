/* Blood splats on walls and floors (re/notes/BLOOD.md, "Splats on walls and floors"). A bullet hit on flesh
 * leaves the flesh decal only on the hit character, for about 2 s. When the engine places that decal
 * (Instincts 0046FEF0, its material in esi; Evolution's own address, see its image profile), this prehook
 * also casts two short rays with the engine's own ray test from the hit point, against static geometry and
 * terrain only (so not the hit body): down to the floor, and on along the shot, behind the target. Where they
 * hit, the engine's own decal routine puts the same flesh decal texture on the world (the hit decal's
 * texture: with the blood mods the game's splat, recoloured; without them the game's red wound mark), as a
 * bullet hole is put on a wall, larger by the strength of the hit and for longer.
 *
 * The engine's decal manager keeps its own pool and drops the oldest; on top of that this keeps splats a
 * little apart and a few a second, so automatic fire does not flood it. fci.ini gfx-blood-splats
 * (RECOMP_FCI_BLOOD_SPLATS) = 0 switches it off, the engine's gore setting too; gfx-blood-splats-size
 * (RECOMP_FCI_BLOOD_SPLATS_SIZE) scales the splats. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#include "recomp_types.h"

extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t alignment);

/* Instincts' addresses; Evolution's image profile defines its own (data/evolution/default.profile.json) */
#ifndef FCI_BLOOD_DECAL_SPAWN
#define FCI_BLOOD_DECAL_SPAWN                                                                                \
    0x0046FFD0u /* ecx = position, eax = normal, edx = texture; size, entity, part, life */
#endif
#ifndef FCI_BLOOD_RAY
#define FCI_BLOOD_RAY                                                                                        \
    0x00376000u /* world, origin, direction, types, flags, max hits, skip, skip; ebx = hits; ret 0x30 */
#endif
#ifndef FCI_BLOOD_WORLD
#define FCI_BLOOD_WORLD 0x006B38F8u /* the physical world, as the bullet's own ray takes it (000EA558) */
#endif
#ifndef FCI_BLOOD_DECAL_TEXTURES
#define FCI_BLOOD_DECAL_TEXTURES 0x006B14E4u /* the hard-coded decals' textures (0046FF79) */
#endif
#ifndef FCI_BLOOD_NO_GORE
#define FCI_BLOOD_NO_GORE 0x006B4AF1u /* a byte: set, the engine leaves out flesh decals and blood sprays */
#endif
/* the hit-effect dispatcher's calls of the decal placement (0046F430), by the blood they go with */
#ifndef FCI_BLOOD_RET_BIG
#define FCI_BLOOD_RET_BIG 0x0046F83Du /* hit kind 5, GFX_Particle_Bullet_Hit_Blood_Big */
#endif
#ifndef FCI_BLOOD_RET_MEDIUM
#define FCI_BLOOD_RET_MEDIUM 0x0046F8B5u /* kind 6, _Medium */
#endif
#ifndef FCI_BLOOD_RET_SMALL
#define FCI_BLOOD_RET_SMALL 0x0046F925u /* kind 7, _Small */
#endif
/* Evolution: one call for kinds 5 to 7; the dispatcher's hit kind is then on the stack, this far above the
 * return address (its frame: ebp+0xC) */
#ifndef FCI_BLOOD_RET_KIND
#define FCI_BLOOD_RET_KIND 0u
#endif
#ifndef FCI_BLOOD_KIND_AT
#define FCI_BLOOD_KIND_AT 0x40u
#endif
/* Evolution's ray takes the world in ebx and the hits on the stack: (origin, direction, types, flags, hits,
 * max hits, skip, skip), ret 0x30 */
#ifndef FCI_BLOOD_RAY_WORLD_IN_EBX
#define FCI_BLOOD_RAY_WORLD_IN_EBX 0u
#endif

#define FLESH_DECAL 6     /* the decal table's GFX_Decal_Bullet_Hit_Flesh_A */
#define WORLD_TYPES 0x101 /* static entities and terrain */
#define RAY_FLAGS   0x100 /* as the scripts' System:RayWorldIntersection */
#define HIT_SIZE                                                                                             \
    0x34 /* a ray hit: dist, collider, part, part id, surface, point (+0x14), normal (+0x20), ... */
#define MAX_HITS     4
#define REACH_DOWN   3.0f /* metres to look for the floor under the hit */
#define REACH_BEHIND 3.0f /* and for a wall behind the target */
#define LIFE       30.0f /* the decal routine's life value (15 for a bullet hole, 2 for the mark on a body) */
#define SPLAT      1.0f  /* a big hit's splat size, before the random part */
#define APART      0.3f  /* closer to a recent splat than this, no new one */
#define RECENT     32
#define PER_SECOND 10

static int state;               /* 0 not yet, 1 on, -1 off */
static int logging;             /* RECOMP_FCI_BLOOD_SPLATS_LOG=1: a line per hit and splat */
static float size_scale = 1.0f; /* RECOMP_FCI_BLOOD_SPLATS_SIZE: the splats' size, times */
static uint32_t scratch;        /* guest memory: hits, then a position and a normal */
static float recent[RECENT][3];
static int nrecent, next_recent;
static ULONGLONG stamps[PER_SECOND];
static int next_stamp;
static uint32_t seed = 0x2545F491u;

static int enabled(void)
{
    if (!state) {
        const char *v = getenv("RECOMP_FCI_BLOOD_SPLATS"), *size = getenv("RECOMP_FCI_BLOOD_SPLATS_SIZE");
        state = v && v[0] == '0' ? -1 : 1;
        logging = getenv("RECOMP_FCI_BLOOD_SPLATS_LOG") != NULL;
        if (size && atof(size) > 0.0)
            size_scale = (float)atof(size);
        if (state > 0 && !(scratch = xbox_HeapAlloc(MAX_HITS * HIT_SIZE + 32, 16)))
            state = -1;
        fprintf(stderr, "[FCI] blood splats: %s\n", state > 0 ? "on" : "off");
    }
    return state > 0;
}

static float random01(void)
{
    seed = seed * 1664525u + 1013904223u;
    return (float)(seed >> 8) / 16777216.0f;
}

static float memf(uint32_t va)
{
    uint32_t u = MEM32(va);
    float f;
    memcpy(&f, &u, 4);
    return f;
}

static void setf(uint32_t va, float f)
{
    uint32_t u;
    memcpy(&u, &f, 4);
    MEM32(va) = u;
}

static uint32_t bits(float f)
{
    uint32_t u;
    memcpy(&u, &f, 4);
    return u;
}

/* the guest registers the calls below change, kept for the hooked function's body */
typedef struct {
    uint32_t eax, ebx, ecx, edx, esi, edi, esp, ebp, seh_ebp;
    double fp[8];
    int fp_top, fp_cmp, df;
    uint16_t fp_cc, fp_cw;
    RecompXmm xmm[8];
} Saved;

static void save(Saved *s)
{
    s->eax = g_eax, s->ebx = g_ebx, s->ecx = g_ecx, s->edx = g_edx, s->esi = g_esi, s->edi = g_edi;
    s->esp = g_esp, s->ebp = g_ebp, s->seh_ebp = g_seh_ebp;
    memcpy(s->fp, g_fp_stack, sizeof s->fp);
    s->fp_top = g_fp_top, s->fp_cmp = g_fp_cmp, s->df = g_df, s->fp_cc = g_fp_cc,
    s->fp_cw = g_fp_control_word;
    s->xmm[0] = g_xmm0, s->xmm[1] = g_xmm1, s->xmm[2] = g_xmm2, s->xmm[3] = g_xmm3;
    s->xmm[4] = g_xmm4, s->xmm[5] = g_xmm5, s->xmm[6] = g_xmm6, s->xmm[7] = g_xmm7;
}

static void restore(const Saved *s)
{
    g_eax = s->eax, g_ebx = s->ebx, g_ecx = s->ecx, g_edx = s->edx, g_esi = s->esi, g_edi = s->edi;
    g_esp = s->esp, g_ebp = s->ebp, g_seh_ebp = s->seh_ebp;
    memcpy(g_fp_stack, s->fp, sizeof s->fp);
    g_fp_top = s->fp_top, g_fp_cmp = s->fp_cmp, g_df = s->df, g_fp_cc = s->fp_cc,
    g_fp_control_word = s->fp_cw;
    g_xmm0 = s->xmm[0], g_xmm1 = s->xmm[1], g_xmm2 = s->xmm[2], g_xmm3 = s->xmm[3];
    g_xmm4 = s->xmm[4], g_xmm5 = s->xmm[5], g_xmm6 = s->xmm[6], g_xmm7 = s->xmm[7];
}

/* the engine's ray test from org along dir (its length is the reach) against walls and terrain: 1 with the
 * first solid hit's point and normal */
static int ray(const float org[3], const float dir[3], float point[3], float normal[3])
{
    recomp_func_t test = recomp_lookup(FCI_BLOOD_RAY);
    uint32_t world = MEM32(FCI_BLOOD_WORLD), n, hit = scratch;
    float reach = sqrtf(dir[0] * dir[0] + dir[1] * dir[1] + dir[2] * dir[2]), dist;
    if (!test || !world)
        return 0;
    for (int i = 0; i < MAX_HITS; i++) {
        setf(hit + i * HIT_SIZE, -1.0f);
        MEM32(hit + i * HIT_SIZE + 4) = 0;
    }
    PUSH32(g_esp, 0); /* nothing skipped */
    PUSH32(g_esp, 0);
    PUSH32(g_esp, MAX_HITS);
    if (FCI_BLOOD_RAY_WORLD_IN_EBX)
        PUSH32(g_esp, hit);
    PUSH32(g_esp, RAY_FLAGS);
    PUSH32(g_esp, WORLD_TYPES);
    for (int k = 2; k >= 0; k--)
        PUSH32(g_esp, bits(dir[k]));
    for (int k = 2; k >= 0; k--)
        PUSH32(g_esp, bits(org[k]));
    if (!FCI_BLOOD_RAY_WORLD_IN_EBX)
        PUSH32(g_esp, world);
    PUSH32(g_esp, 0); /* the return address: its ret 0x30 pops it and the arguments */
    g_ebx = FCI_BLOOD_RAY_WORLD_IN_EBX ? world : hit;
    test();
    n = g_eax;
    dist = memf(hit);
    if (!n || n > MAX_HITS || !(dist > 0.0f) || dist > reach * 1.01f)
        return 0;
    for (int k = 0; k < 3; k++) {
        point[k] = memf(hit + 0x14 + 4 * k);
        normal[k] = memf(hit + 0x20 + 4 * k);
    }
    return 1;
}

static int crowded(const float p[3])
{
    for (int i = 0; i < nrecent; i++) {
        float dx = recent[i][0] - p[0], dy = recent[i][1] - p[1], dz = recent[i][2] - p[2];
        if (dx * dx + dy * dy + dz * dz < APART * APART)
            return 1;
    }
    return 0;
}

static int too_many(void)
{
    ULONGLONG now = GetTickCount64();
    return stamps[next_stamp] && now - stamps[next_stamp] < 1000;
}

/* the engine's decal routine on the world (no entity), as for a bullet hole */
static void splat(const char *where, const float p[3], const float n[3], float size, uint32_t texture)
{
    recomp_func_t place = recomp_lookup(FCI_BLOOD_DECAL_SPAWN);
    uint32_t at = scratch + MAX_HITS * HIT_SIZE;
    if (!place || crowded(p) || too_many())
        return;
    for (int k = 0; k < 3; k++) {
        setf(at + 4 * k, p[k]);
        setf(at + 12 + 4 * k, n[k]);
    }
    PUSH32(g_esp, bits(LIFE));
    PUSH32(g_esp, 0); /* part */
    PUSH32(g_esp, 0); /* no entity: the world */
    PUSH32(g_esp, bits(size));
    PUSH32(g_esp, 0); /* the return address, which its ret pops */
    g_ecx = at;
    g_eax = at + 12;
    g_edx = texture; /* Instincts' routine takes the texture in edx, Evolution's in edi */
    g_edi = texture;
    place();
    g_esp += 16; /* the caller pops the arguments */
    if (logging)
        fprintf(stderr, "[FCI] blood splat on the %s at %.2f %.2f %.2f (normal %.2f %.2f %.2f), size %.2f\n",
                where, p[0], p[1], p[2], n[0], n[1], n[2], size);
    memcpy(recent[next_recent], p, sizeof recent[0]);
    next_recent = (next_recent + 1) % RECENT;
    if (nrecent < RECENT)
        nrecent++;
    stamps[next_stamp] = GetTickCount64();
    next_stamp = (next_stamp + 1) % PER_SECOND;
}

/* the decal placement (esi = the material's entry; entity, position, normal, part, life; cdecl): on the
 * flesh decal of a hit character, splats on the floor below and the wall behind */
void fci_prehook_0046FEF0(void)
{
    uint32_t material = g_esi, from = MEM32(g_esp), entity = MEM32(g_esp + 4);
    uint32_t pos = MEM32(g_esp + 8), nrm = MEM32(g_esp + 12), texture;
    float p[3], n[3], len, scale, down[3] = {0, 0, -REACH_DOWN}, behind[3], hp[3], hn[3], floor_at[3] = {0};
    int on_floor = 0;
    Saved s;
    if (!entity || !material || MEM32(material + 0xC) != FLESH_DECAL || MEM8(FCI_BLOOD_NO_GORE) || !enabled())
        return;
    texture = MEM32(FCI_BLOOD_DECAL_TEXTURES + 4 * FLESH_DECAL);
    if (texture == 0xFFFFFFFFu || !pos || !nrm)
        return;
    if (FCI_BLOOD_RET_KIND && from == FCI_BLOOD_RET_KIND) {
        uint32_t kind = MEM32(g_esp + FCI_BLOOD_KIND_AT);
        scale = kind == 5 ? 1.0f : kind == 7 ? 0.55f : 0.75f;
    } else {
        scale = from == FCI_BLOOD_RET_BIG ? 1.0f : from == FCI_BLOOD_RET_SMALL ? 0.55f : 0.75f;
    }
    for (int k = 0; k < 3; k++) {
        p[k] = memf(pos + 4 * k);
        n[k] = memf(nrm + 4 * k);
    }
    len = sqrtf(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
    scale *= size_scale;
    if (logging)
        fprintf(stderr, "[FCI] blood hit at %.2f %.2f %.2f (normal %.2f %.2f %.2f), scale %.2f\n", p[0], p[1],
                p[2], n[0], n[1], n[2], scale);
    save(&s);
    if (ray(p, down, hp, hn)) {
        splat("floor", hp, hn, SPLAT * scale * (0.8f + 0.4f * random01()), texture);
        memcpy(floor_at, hp, sizeof floor_at);
        on_floor = 1;
    }
    if (len > 0.1f) { /* the normal faces the shooter: on along the shot is against it */
        for (int k = 0; k < 3; k++)
            behind[k] = -n[k] / len * REACH_BEHIND;
        if (ray(p, behind, hp, hn)) {
            float dx = hp[0] - floor_at[0], dy = hp[1] - floor_at[1], dz = hp[2] - floor_at[2];
            if (!on_floor || dx * dx + dy * dy + dz * dz > 0.5f * 0.5f)
                splat("wall", hp, hn, SPLAT * scale * (0.7f + 0.4f * random01()), texture);
        } else if (logging) {
            fprintf(stderr, "[FCI] blood: no wall within %.0f m behind\n", REACH_BEHIND);
        }
    }
    restore(&s);
}
