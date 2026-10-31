/* Blood splats on walls and floors (re/notes/BLOOD.md, "Splats on walls and floors"). A bullet hit on flesh
 * leaves the flesh decal only on the hit character, for about 2 s. When the engine places that decal
 * (Instincts 0046FEF0, its material in esi; Evolution's own address, see its image profile), this prehook
 * also casts two short rays with the engine's own ray test from the hit point, against static geometry and
 * terrain only (so not the hit body): down to the floor, and on along the shot, behind the target. Where they
 * hit, the engine's own decal routine puts the same flesh decal texture on the world (the hit decal's
 * texture: with the blood mods the game's splat, recoloured; without them the game's red wound mark), as a
 * bullet hole is put on a wall, larger by the strength of the hit and for longer (gfx-blood-splats-life
 * seconds), and drawn as a stain the ground's light and shadow show through ("lit like the ground" below).
 *
 * The engine's decal manager keeps every decal until its life is over, with no limit ("The decal manager");
 * this keeps splats a little apart and a few a second, so automatic fire does not flood it. fci.ini
 * gfx-blood-splats (RECOMP_FCI_BLOOD_SPLATS) = 0 switches it off, the engine's gore setting too;
 * gfx-blood-splats-size (RECOMP_FCI_BLOOD_SPLATS_SIZE) scales the splats. */
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
/* the decal manager's drawing (0045B110) hands its batches to the renderer here: quads (0023FBB0) and world
 * decals over 0.2 m laid onto the terrain (0045B770 -> 0024D470) */
#ifndef FCI_BLOOD_QUAD_BATCH_RET
#define FCI_BLOOD_QUAD_BATCH_RET 0x0045B5C7u
#endif
/* the drawn decals' owner (0 the world) in the drawing's frame, from the quad batch's entry: [esp+0xDC] at
 * 0045B52D, four arguments and the return address down */
#ifndef FCI_BLOOD_QUAD_OWNER_AT
#define FCI_BLOOD_QUAD_OWNER_AT 0x000000F0u
#endif
#ifndef FCI_BLOOD_QUAD_OWNER_EBP
#define FCI_BLOOD_QUAD_OWNER_EBP 0u /* Evolution: in its ebp frame */
#endif
/* the batches' arguments at their entry: count, texture, state, flags (Evolution: the texture in a register,
 * ebx for quads, eax for the terrain, 0 here) */
#ifndef FCI_BLOOD_QUAD_STATE_AT
#define FCI_BLOOD_QUAD_STATE_AT 0x0000000Cu
#endif
#ifndef FCI_BLOOD_QUAD_TEXTURE_AT
#define FCI_BLOOD_QUAD_TEXTURE_AT 0x00000008u
#endif
#ifndef FCI_BLOOD_TERRAIN_STATE_AT
#define FCI_BLOOD_TERRAIN_STATE_AT 0x0000000Cu
#endif
#ifndef FCI_BLOOD_TERRAIN_TEXTURE_AT
#define FCI_BLOOD_TERRAIN_TEXTURE_AT 0x00000008u
#endif
/* a decal's light colour (00460E20): the out vector in edi (0) or on the stack, and its arguments' bytes */
#ifndef FCI_BLOOD_LIGHT_OUT_AT
#define FCI_BLOOD_LIGHT_OUT_AT 0u
#endif
#ifndef FCI_BLOOD_LIGHT_ARGS
#define FCI_BLOOD_LIGHT_ARGS 4u
#endif
#ifndef FCI_BLOOD_TERRAIN_BATCH_RET
#define FCI_BLOOD_TERRAIN_BATCH_RET 0x0045B889u
#endif
#ifndef FCI_BLOOD_ENGINE3D
#define FCI_BLOOD_ENGINE3D 0x006B3900u /* the 3D engine; its decal manager at +0x2C4 (0047006E) */
#endif

#define FLESH_DECAL 6     /* the decal table's GFX_Decal_Bullet_Hit_Flesh_A */
#define WORLD_TYPES 0x101 /* static entities and terrain */
#define RAY_FLAGS   0x100 /* as the scripts' System:RayWorldIntersection */
#define HIT_SIZE                                                                                             \
    0x34 /* a ray hit: dist, collider, part, part id, surface, point (+0x14), normal (+0x20), ... */
#define MAX_HITS     4
#define REACH_DOWN   3.0f /* metres to look for the floor under the hit */
#define REACH_BEHIND 3.0f /* and for a wall behind the target */
#define LIFE       300.0f /* seconds (RECOMP_FCI_BLOOD_SPLATS_LIFE); a bullet hole has 15, a body's mark 2 */
#define MAX_LIFE   3600.0
#define SPLAT      1.0f /* a big hit's splat size, before the random part */
#define APART      0.3f /* closer to a recent splat than this, no new one */
#define RECENT     32
#define PER_SECOND 10

static int state;               /* 0 not yet, 1 on, -1 off */
static int logging;             /* RECOMP_FCI_BLOOD_SPLATS_LOG=1: a line per hit and splat */
static float size_scale = 1.0f; /* RECOMP_FCI_BLOOD_SPLATS_SIZE: the splats' size, times */
static float life = LIFE;       /* RECOMP_FCI_BLOOD_SPLATS_LIFE: a splat's life, in seconds */
static uint32_t scratch;        /* guest memory: hits, then a position and a normal */
static float recent[RECENT][3];
static int nrecent, next_recent;
static ULONGLONG stamps[PER_SECOND];
static int next_stamp;
static uint32_t seed = 0x2545F491u;
static int placing;    /* a splat is being placed */
static int on_terrain; /* the last ray hit the terrain, not an object */

static int enabled(void)
{
    if (!state) {
        const char *v = getenv("RECOMP_FCI_BLOOD_SPLATS"), *size = getenv("RECOMP_FCI_BLOOD_SPLATS_SIZE");
        const char *secs = getenv("RECOMP_FCI_BLOOD_SPLATS_LIFE");
        state = v && v[0] == '0' ? -1 : 1;
        logging = getenv("RECOMP_FCI_BLOOD_SPLATS_LOG") != NULL;
        if (size && atof(size) > 0.0)
            size_scale = (float)atof(size);
        if (secs && atof(secs) >= 1.0)
            life = (float)(atof(secs) < MAX_LIFE ? atof(secs) : MAX_LIFE);
        if (state > 0 && !(scratch = xbox_HeapAlloc(MAX_HITS * HIT_SIZE + 32, 16)))
            state = -1;
        fprintf(stderr, "[FCI] blood splats: %s, %.0f s\n", state > 0 ? "on" : "off", life);
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
    on_terrain = MEM32(hit + 0x2C) != 0; /* the hit's bTerrain */
    return 1;
}

/* the log's count of the world's decals: the engine's decal manager is a std::multimap by owner entity
 * (0 the world) with no size limit; each frame (0045BAA0) adds the frame time to every decal's age and
 * erases it past its life, and the last second fades it out. A node: +0 left, +4 parent, +8 right, +0xC the
 * owner, +0x34 age, +0x38 life, +0x4C the light colour taken at its placing, +0x50 the texture, +0x55 nil. */
static void census(uint32_t texture)
{
    uint32_t e3d = MEM32(FCI_BLOOD_ENGINE3D), mgr = e3d ? MEM32(e3d + 0x2C4) : 0, head, n;
    int splats = 0, others = 0, steps = 0;
    float oldest = 0.0f;
    uint32_t colour = 0, other_colour = 0;
    if (!mgr || !(head = MEM32(mgr + 4)))
        return;
    for (n = MEM32(head); n && n != head && steps < 100000; steps++) {
        uint32_t r = MEM32(n + 8), p;
        if (!MEM32(n + 0xC)) {
            if (MEM32(n + 0x50) == texture) {
                splats++;
                colour = MEM32(n + 0x4C);
                if (memf(n + 0x34) > oldest)
                    oldest = memf(n + 0x34);
            } else {
                others++;
                other_colour = MEM32(n + 0x4C);
            }
        }
        if (!MEM8(r + 0x55)) { /* the next in order: the right subtree's leftmost, or up past right links */
            for (n = r; !MEM8(MEM32(n) + 0x55);)
                n = MEM32(n);
        } else {
            while (!MEM8((p = MEM32(n + 4)) + 0x55) && n == MEM32(p + 8))
                n = p;
            n = p;
        }
    }
    fprintf(stderr,
            "[FCI] blood: the world's decals: %d splats (the oldest %.0f s of %.0f, light %06X), %d others "
            "(light "
            "%06X)\n",
            splats, oldest, life, colour & 0xFFFFFF, others, other_colour & 0xFFFFFF);
}

/* ---- lit like the ground ----
 * The engine draws a decal as texture x a light colour taken once at its placing x 2, alpha blended
 * (SRC_ALPHA, ONE_MINUS_SRC_ALPHA). Outdoors that colour is the level's ambient wherever the decal lies, so a
 * bright splat glows in the shade; the game's own decals are dark and do not show it. Splats are drawn
 * instead as a stain: the frame times the texture's colour (the renderer's blend mode 7, DST_COLOR x ZERO),
 * cut to the splatter by the alpha test (from alpha 0x80), with a light colour of one half (texture x 1), so
 * the ground's own light and shadow show through in the blood's colour. RECOMP_FCI_BLOOD_SPLATS_LIT=0
 * (fci.ini gfx-blood-splats-lit) keeps the engine's way. */
#define BLEND_MODE  0x0000000Fu /* the renderer's state (00243220): the blend mode */
#define ALPHA_TEST  0x03800000u /* and the alpha test: 0x1800000 is from 0x80 up */
#define STATE_ALPHA 1u          /* SRC_ALPHA, ONE_MINUS_SRC_ALPHA */
#define STATE_STAIN (7u | 0x01800000u)
#define STAIN_LIGHT 0.5f

static int lit = -1;

static int lit_like_ground(void)
{
    if (lit < 0) {
        const char *v = getenv("RECOMP_FCI_BLOOD_SPLATS_LIT");
        lit = !(v && v[0] == '0');
    }
    return lit;
}

/* the decal's light colour (edi = out, [esp+4] = the position; ret 4): one half for a splat being placed */
int fci_gate_00460E20(void)
{
    uint32_t out = FCI_BLOOD_LIGHT_OUT_AT ? MEM32(g_esp + FCI_BLOOD_LIGHT_OUT_AT) : g_edi;
    if (!placing || !lit_like_ground() || !out)
        return 0;
    setf(out, STAIN_LIGHT);
    setf(out + 4, STAIN_LIGHT);
    setf(out + 8, STAIN_LIGHT);
    g_eax = out;
    g_esp += 4 + FCI_BLOOD_LIGHT_ARGS; /* its ret */
    return 1;
}

/* a decal batch from the decal manager's drawing (its state argument, the texture): a world splat's as a
 * stain (the flesh decal's marks on bodies stay as they were) */
static void stain(uint32_t state_at, uint32_t texture, uint32_t owner)
{
    uint32_t st = MEM32(g_esp + state_at);
    if (state <= 0 || !lit_like_ground() || owner || (st & BLEND_MODE) != STATE_ALPHA
        || texture != MEM32(FCI_BLOOD_DECAL_TEXTURES + 4 * FLESH_DECAL))
        return;
    MEM32(g_esp + state_at) = (st & ~(BLEND_MODE | ALPHA_TEST)) | STATE_STAIN;
}

/* decals as quads: the world's small ones and those on entities */
void fci_prehook_0023FBB0(void)
{
    if (MEM32(g_esp) != FCI_BLOOD_QUAD_BATCH_RET)
        return;
    stain(FCI_BLOOD_QUAD_STATE_AT,
          FCI_BLOOD_QUAD_TEXTURE_AT ? MEM32(g_esp + FCI_BLOOD_QUAD_TEXTURE_AT) : g_ebx,
          MEM32((FCI_BLOOD_QUAD_OWNER_EBP ? g_ebp : g_esp) + FCI_BLOOD_QUAD_OWNER_AT));
}

/* the world's decals over 0.2 m, laid onto the terrain */
void fci_prehook_0024D470(void)
{
    if (MEM32(g_esp) != FCI_BLOOD_TERRAIN_BATCH_RET)
        return;
    stain(FCI_BLOOD_TERRAIN_STATE_AT,
          FCI_BLOOD_TERRAIN_TEXTURE_AT ? MEM32(g_esp + FCI_BLOOD_TERRAIN_TEXTURE_AT) : g_eax, 0);
}

/* the decal manager lays a world decal over 0.2 m onto the terrain's grid (0045B770), wherever it was placed:
 * one on an object (a wall, a floor of planks) stays a quad on it, at most this big */
#define OBJECT_SPLAT 0.19f

static float fit(float size) { return on_terrain || size < OBJECT_SPLAT ? size : OBJECT_SPLAT; }

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
    PUSH32(g_esp, bits(life));
    PUSH32(g_esp, 0); /* part */
    PUSH32(g_esp, 0); /* no entity: the world */
    PUSH32(g_esp, bits(size));
    PUSH32(g_esp, 0); /* the return address, which its ret pops */
    g_ecx = at;
    g_eax = at + 12;
    g_edx = texture; /* Instincts' routine takes the texture in edx, Evolution's in edi */
    g_edi = texture;
    placing = 1; /* the light colour's gate below */
    place();
    placing = 0;
    g_esp += 16; /* the caller pops the arguments */
    if (logging) {
        fprintf(stderr,
                "[FCI] blood splat on the %s at %.2f %.2f %.2f (normal %.2f %.2f %.2f), size %.2f, %s\n",
                where, p[0], p[1], p[2], n[0], n[1], n[2], size, on_terrain ? "terrain" : "object");
        census(texture);
    }
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
    static int test = -1;
    if (test < 0)
        test = getenv("RECOMP_FCI_BLOOD_SPLATS_TEST") != NULL;
    if (test && !entity && material && MEM32(material + 0xC) != FLESH_DECAL && pos && nrm && enabled()) {
        /* a test aid: a splat 0.6 m beside each bullet hole on the world, to compare the two in a capture */
        float q[3], t[3] = {1, 0, 0};
        texture = MEM32(FCI_BLOOD_DECAL_TEXTURES + 4 * FLESH_DECAL);
        for (int k = 0; k < 3; k++)
            n[k] = memf(nrm + 4 * k);
        if (fabsf(n[0]) > 0.8f)
            t[0] = 0, t[1] = 1;
        for (int k = 0; k < 3; k++)
            q[k] = memf(pos + 4 * k) + 0.6f * t[k];
        save(&s);
        if (texture != 0xFFFFFFFFu)
            splat("test", q, n, 0.5f * size_scale, texture);
        restore(&s);
        return;
    }
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
        splat("floor", hp, hn, fit(SPLAT * scale * (0.8f + 0.4f * random01())), texture);
        memcpy(floor_at, hp, sizeof floor_at);
        on_floor = 1;
    }
    if (len > 0.1f) { /* the normal faces the shooter: on along the shot is against it */
        for (int k = 0; k < 3; k++)
            behind[k] = -n[k] / len * REACH_BEHIND;
        if (ray(p, behind, hp, hn)) {
            float dx = hp[0] - floor_at[0], dy = hp[1] - floor_at[1], dz = hp[2] - floor_at[2];
            if (!on_floor || dx * dx + dy * dy + dz * dz > 0.5f * 0.5f)
                splat("wall", hp, hn, fit(SPLAT * scale * (0.7f + 0.4f * random01())), texture);
        } else if (logging) {
            fprintf(stderr, "[FCI] blood: no wall within %.0f m behind\n", REACH_BEHIND);
        }
    }
    restore(&s);
}
