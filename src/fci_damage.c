/* Weapon strength and enemy damage (re/notes/WEAPONS.md, "Damage"): the mod menu's two settings
 * (fci_mods_weapon_strength, fci_mods_enemy_damage, in percent) scale the damage Jack deals to characters
 * and the damage others deal to him, live. The game's scripts apply damage (GameRules:OnDamage and
 * ApplyDamage in lua.dat take hit.damage, times their body-part tables, off the target's health); the
 * engine builds the hit tables, and these hooks scale hit.damage on its way there:
 *
 *   bullets     the hit function (Instincts 000EBEE0: the hit, its damage at +0x24, target +0x28, shooter
 *               +0x34) builds the hit table, runs the weapon's OnHit scripts (000E89D0) and then the
 *               target's OnDamage. The table's damage is scaled after the OnHit scripts, which pick the
 *               blood's size by it, so the blood stays as it was.
 *   explosions  the explosion code sets each target's hit table damage through the script object's
 *               SetValue(key, float) (002985A0); the call from there (return address 000B672B) is scaled,
 *               the shooter and the target read from the explosion code's frame.
 *   melee       the melee attack (0007A1B0, ecx = the attacker's player object) runs the BasicPlayer
 *               MeleeAttack script, whose hit.damage is the attacker's melee_damage (+0x1A4): scaled for
 *               the call. An enemy's melee is scaled by the enemy damage whoever it hits.
 *
 * A character is an entity whose container (+0x23C) is a player object (its class's QueryContainerInterface
 * that of Jack's): the AI people and creatures and Jack, not vehicles or props. Jack is the entity of the game's first player
 * slot. At 100 % nothing is touched. RECOMP_FCI_DAMAGE_LOG=1 prints each scaled hit with the target's
 * health before and after. Evolution's addresses come from its image profile. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "recomp_types.h"
#include "fci_mods.h"

/* Instincts' addresses; Evolution's image profile defines its own (data/evolution/default.profile.json) */
#ifndef FCI_DAMAGE_HIT
#define FCI_DAMAGE_HIT 0x000EBEE0u /* the bullet hit (ebx = weapon; hit, params, first bullet), ret 0xC */
#endif
#ifndef FCI_DAMAGE_ONHIT
#define FCI_DAMAGE_ONHIT 0x000E89D0u /* the weapon's OnHit scripts (esi = weapon; table, hit params) */
#endif
#ifndef FCI_DAMAGE_MELEE
#define FCI_DAMAGE_MELEE 0x0007A1B0u /* the melee attack (ecx = player, eax = direction; 3 args) */
#endif
#ifndef FCI_DAMAGE_EXPLOSION_RET
#define FCI_DAMAGE_EXPLOSION_RET 0x000B672Bu /* the explosion's SetValue("damage", per-target damage) */
#endif
/* the explosion's shooter entity: in its frame at esp (0) or ebp (1) plus this, at the SetValue call */
#ifndef FCI_DAMAGE_EXPLOSION_SHOOTER_EBP
#define FCI_DAMAGE_EXPLOSION_SHOOTER_EBP 0u
#endif
#ifndef FCI_DAMAGE_EXPLOSION_SHOOTER_AT
#define FCI_DAMAGE_EXPLOSION_SHOOTER_AT 0x00000048u /* [esp + 0x3C] at 000B66EE; the call's two arguments */
#endif
/* the explosion's target entity: ebp (0) or ebx (1) */
#ifndef FCI_DAMAGE_EXPLOSION_TARGET_EBX
#define FCI_DAMAGE_EXPLOSION_TARGET_EBX 0u
#endif
#ifndef FCI_DAMAGE_KEY
#define FCI_DAMAGE_KEY 0x005FC1ACu /* the game's "damage", the hit tables' key */
#endif
#ifndef FCI_DAMAGE_GAME
#define FCI_DAMAGE_GAME 0x006B3984u /* the game object; its player slots at +0x28 (0004CD60) */
#endif
#ifndef FCI_DAMAGE_PLAYER_SLOT
#define FCI_DAMAGE_PLAYER_SLOT 0x00000028u /* the first player slot; its entity id at +0x30 */
#endif
#ifndef FCI_DAMAGE_HEALTH
#define FCI_DAMAGE_HEALTH 0x00000160u /* the player object's health (the script property cnt.health) */
#endif
#ifndef FCI_DAMAGE_MELEE_DAMAGE
#define FCI_DAMAGE_MELEE_DAMAGE 0x000001A4u /* the player object's melee_damage */
#endif
#define ENTITY_ID        0xA4  /* an entity's id (the hit tables' target_id) */
#define ENTITY_CONTAINER 0x23C /* its container, a player object for characters (its +4 the entity) */
#define SET_VALUE_FLOAT  0x34  /* the script object's SetValue(key, float), thiscall, ret 8 */

static int logging = -1;

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

static int log_on(void)
{
    if (logging < 0) {
        logging = getenv("RECOMP_FCI_DAMAGE_LOG") != NULL;
        fprintf(stderr, "[FCI] damage: weapon strength %d %%, enemy damage %d %%\n",
                fci_mods_weapon_strength(), fci_mods_enemy_damage());
    }
    return logging;
}

/* Jack's entity id, 0 when there is no player */
static uint32_t player_id(void)
{
    uint32_t game = MEM32(FCI_DAMAGE_GAME), slot = game ? MEM32(game + FCI_DAMAGE_PLAYER_SLOT) : 0;
    return slot ? MEM32(slot + 0x30) : 0;
}

static uint32_t entity_id(uint32_t entity) { return entity ? MEM32(entity + ENTITY_ID) : 0; }

/* the player object of a character entity, 0 otherwise: a container pointing back at it whose class is a
 * player's like Jack's (the AI people and creatures have classes of their own, derived from it: the same
 * QueryContainerInterface, vtable +0x10; vehicles and the like have another) */
static uint32_t character(uint32_t entity, uint32_t jack)
{
    uint32_t c = entity ? MEM32(entity + ENTITY_CONTAINER) : 0, j = jack ? MEM32(jack + ENTITY_CONTAINER) : 0;
    if (!c || !j || MEM32(c + 4) != entity || !MEM32(c) || MEM32(MEM32(c) + 0x10) != MEM32(MEM32(j) + 0x10))
        return 0;
    return c;
}

/* the factor for a hit of shooter on target (entities; 0 when unknown): the weapon strength when Jack hits
 * a character, the enemy damage when another hits Jack, else 1 */
static float factor(uint32_t shooter, uint32_t target, uint32_t *jack_out)
{
    uint32_t me = player_id(), jack = 0;
    if (!me || !target)
        return 1.0f;
    if (entity_id(target) == me)
        jack = target;
    else if (entity_id(shooter) == me)
        jack = shooter;
    if (jack_out)
        *jack_out = jack;
    if (!jack)
        return 1.0f;
    if (shooter && jack == shooter && target != shooter)
        return character(target, jack) ? fci_mods_weapon_strength() / 100.0f : 1.0f;
    if (jack == target && shooter != target)
        return fci_mods_enemy_damage() / 100.0f;
    return 1.0f;
}

/* the guest registers a call from here changes */
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

/* the hooked function's body, called from its gate: the gate's next call (the busy flag set) passes */
static void body(uint32_t va, int *busy)
{
    recomp_func_t f = recomp_lookup(va);
    *busy = 1;
    if (f)
        f();
    *busy = 0;
}

static float health(uint32_t entity, uint32_t jack)
{
    uint32_t c = character(entity, jack);
    return c ? memf(c + FCI_DAMAGE_HEALTH) : -1.0f;
}

/* ---- bullets ---- */

void fci_input_mouse_inject(int dx, int dy); /* fci_input.c: motion as from the mouse, 0.05 degrees a count */

/* RECOMP_FCI_DAMAGE_TEST_AIM=1, a test aid: Jack's shots give his aim (the hit's direction, +0x18), an
 * enemy's hit on him where it came from; at Jack's next shot the difference is turned with mouse counts */
static void test_aim(uint32_t hit, int by_jack, int on_jack)
{
    static int on = -1, have_from;
    static float from[3];
    float d[3], ya, yf, pa, pf, turn;
    if (on < 0)
        on = getenv("RECOMP_FCI_DAMAGE_TEST_AIM") != NULL;
    if (!on || by_jack == on_jack)
        return;
    for (int k = 0; k < 3; k++)
        d[k] = memf(hit + 0x18 + 4 * k);
    if (on_jack) {
        for (int k = 0; k < 3; k++)
            from[k] = -d[k];
        have_from = 1;
        return;
    }
    if (!have_from)
        return;
    ya = atan2f(d[1], d[0]) * 57.29578f;
    yf = atan2f(from[1], from[0]) * 57.29578f;
    pa = atan2f(d[2], sqrtf(d[0] * d[0] + d[1] * d[1])) * 57.29578f;
    pf = atan2f(from[2], sqrtf(from[0] * from[0] + from[1] * from[1])) * 57.29578f;
    turn = yf - ya;
    turn -= 360.0f * floorf((turn + 180.0f) / 360.0f);
    if (fabsf(turn) > 3.0f || fabsf(pf - pa) > 3.0f)
        fci_input_mouse_inject((int)(-turn / 0.05f), (int)(-(pf - pa) / 0.05f)); /* right and down positive */
    have_from = 0;
}

static int hit_busy, onhit_busy;
static uint32_t pending_hit; /* the hit whose table the OnHit gate scales */
static float pending_factor = 1.0f;

/* the bullet hit: the factor for the OnHit gate, and with the log the target's health around it */
int fci_gate_000EBEE0(void)
{
    uint32_t hit = MEM32(g_esp + 4), shooter, target, jack = 0;
    float f, before;
    int logged;
    if (hit_busy || !hit)
        return 0;
    shooter = MEM32(hit + 0x34);
    target = MEM32(hit + 0x28);
    f = factor(shooter, target, &jack);
    {
        static int seen;
        uint32_t me = player_id();
        test_aim(hit, me && entity_id(shooter) == me, me && entity_id(target) == me);
        if (!seen && me && entity_id(shooter) == me && log_on()) { /* the player slot read right */
            seen = 1;
            fprintf(stderr, "[FCI] damage: Jack's first shot (entity %08X) hit %08X%s\n", me,
                    entity_id(target), target && character(target, shooter) ? ", a character" : "");
        }
    }
    logged = log_on() && jack && character(target, jack); /* with the log, every hit of Jack or on him */
    if (f == 1.0f && !logged)
        return 0;
    if (f != 1.0f) {
        pending_hit = hit;
        pending_factor = f;
    }
    if (!logged) {
        body(FCI_DAMAGE_HIT, &hit_busy);
    } else {
        before = health(target, jack);
        body(FCI_DAMAGE_HIT, &hit_busy);
        fprintf(stderr, "[FCI] damage: %s hit %08X, damage %.1f x %.2f, health %.1f -> %.1f\n",
                jack == shooter ? "Jack's" : "an enemy's", entity_id(target), memf(hit + 0x24), f, before,
                health(target, jack));
    }
    pending_hit = 0;
    pending_factor = 1.0f;
    return 1;
}

/* the weapon's OnHit scripts ran with the game's damage (they pick the blood by it); the target's OnDamage
 * that follows gets the scaled one */
int fci_gate_000E89D0(void)
{
    uint32_t table = MEM32(g_esp + 4), hit = pending_hit, setter;
    float f = pending_factor;
    Saved s;
    if (onhit_busy || !hit || !table)
        return 0;
    pending_hit = 0;
    body(FCI_DAMAGE_ONHIT, &onhit_busy);
    if (!(setter = MEM32(MEM32(table) + SET_VALUE_FLOAT)) || !recomp_lookup(setter))
        return 1;
    save(&s);
    {
        float scaled = memf(hit + 0x24) * f;
        uint32_t u;
        memcpy(&u, &scaled, 4);
        PUSH32(g_esp, u);
        PUSH32(g_esp, FCI_DAMAGE_KEY);
        PUSH32(g_esp, 0); /* the return address, which its ret 8 pops with the arguments */
        g_ecx = table;
        recomp_lookup(setter)();
    }
    restore(&s);
    return 1;
}

/* ---- explosions ---- */

/* the script object's SetValue(key, float): the explosion's damage for one target */
void fci_prehook_002985A0(void)
{
    uint32_t shooter, target, jack = 0;
    float f, d;
    if (MEM32(g_esp) != FCI_DAMAGE_EXPLOSION_RET)
        return;
    shooter = MEM32((FCI_DAMAGE_EXPLOSION_SHOOTER_EBP ? g_ebp : g_esp) + FCI_DAMAGE_EXPLOSION_SHOOTER_AT);
    target = FCI_DAMAGE_EXPLOSION_TARGET_EBX ? g_ebx : g_ebp;
    if ((f = factor(shooter, target, &jack)) == 1.0f)
        return;
    d = memf(g_esp + 8);
    setf(g_esp + 8, d * f);
    if (log_on())
        fprintf(stderr, "[FCI] damage: %s explosion on %08X, damage %.1f x %.2f, health %.1f\n",
                jack == shooter ? "Jack's" : "an enemy's", entity_id(target), d, f, health(target, jack));
}

/* ---- melee ---- */

static int melee_busy;

/* the melee attack of ecx's player: its melee_damage scaled for the call */
int fci_gate_0007A1B0(void)
{
    uint32_t attacker = g_ecx, entity, me = player_id();
    float f, d;
    if (melee_busy || !attacker || !me || !(entity = MEM32(attacker + 4)))
        return 0;
    f = (entity_id(entity) == me ? fci_mods_weapon_strength() : fci_mods_enemy_damage()) / 100.0f;
    if (f == 1.0f)
        return 0;
    d = memf(attacker + FCI_DAMAGE_MELEE_DAMAGE);
    setf(attacker + FCI_DAMAGE_MELEE_DAMAGE, d * f);
    body(FCI_DAMAGE_MELEE, &melee_busy);
    setf(attacker + FCI_DAMAGE_MELEE_DAMAGE, d);
    if (log_on())
        fprintf(stderr, "[FCI] damage: %s melee, damage %.1f x %.2f\n",
                entity_id(entity) == me ? "Jack's" : "an enemy's", d, f);
    return 1;
}
