/* The Halo rifles' displays (re/notes/WEAPONS.md "The magazine count and the heading", re/notes/MODELS.md
 * "Counter displays"): what the renderer draws into a counter texture (xbr/fci_counter.cpp) comes from here.
 *
 *   The rounds in the magazine: the HUD's own number. The HUD's update passes it each frame to the function that
 *   sets the counter beside the bullet icon (Instincts 001A9480, Evolution 0013598A; [esp+4] = the number,
 *   capped at the clip's size as the HUD shows it); a prehook keeps it. It follows weapon switches, reloads and
 *   pickups as the HUD does.
 *   The heading: Player_ProcessInput's prehook (fci_aim.c) hands over the yaw this frame's turn leaves (the
 *   block's angles minus turnYaw, re/notes/INPUT-CAMERA.md), so the needle turns with the view. North is the
 *   HUD's: its compass strip shows yaw + 90 + an offset a level may set (Game.SetCompassOffset), which the
 *   strip's function (Instincts 001AA440, Evolution 00136799; eax = HUD) adds from the HUD; a prehook keeps that.
 *
 * The renderer runs up to a frame behind the game code. Each value is kept with the frame the title is recording
 * (its count of presents, fci_counter_frame), and the renderer asks for the frame it draws: digits, needle and
 * HUD change in the same picture. */
#include <math.h>
#include <stdint.h>
#include <windows.h>

#include "recomp_types.h"

/* the HUD's compass offset in degrees (Game.SetCompassOffset; Instincts 000B8AAA); another executable's
 * profile gives its own (Evolution: 0x328) */
#ifndef FCI_HUD_COMPASS_OFFSET
#define FCI_HUD_COMPASS_OFFSET 0x2A4u
#endif
#define FRAMES 8 /* recent frames kept */

uint64_t fci_counter_frame(void); /* xbr/fci_counter.cpp: the frame the title is recording */

typedef struct {
    volatile LONG64 frame; /* -1: never written */
    volatile LONG rounds;  /* -1: unknown */
    volatile LONG known;   /* the yaw was set */
    volatile float yaw;    /* degrees, falling to the right */
    volatile float offset; /* the HUD's compass offset, degrees */
} State;

static State ring[FRAMES] = {
        {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0},
        {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0}, {-1, -1, 0, 0, 0},
};
static volatile LONG64 newest = -1; /* the latest frame written */

/* this frame's entry, carried over from the latest one when it is new (the title thread alone writes) */
static State *now_entry(void)
{
    LONG64 f = (LONG64)fci_counter_frame();
    State *s = &ring[f % FRAMES];
    if (s->frame != f) {
        if (newest >= 0) {
            const State *from = &ring[newest % FRAMES];
            s->rounds = from->rounds;
            s->known = from->known;
            s->yaw = from->yaw;
            s->offset = from->offset;
        }
        MemoryBarrier();
        s->frame = f;
        newest = f;
    }
    return s;
}

/* the HUD's counter beside the bullet icon (Instincts; Evolution's 0013598A shares it): [esp+4] = the number */
void fci_prehook_001A9480(void) { now_entry()->rounds = (LONG)MEM32(g_esp + 4); }

/* the HUD's compass strip (Instincts; Evolution's 00136799 shares it): eax = HUD, [esp+4] = yaw + 90 */
void fci_prehook_001AA440(void)
{
    float offset = MEMF(g_eax + FCI_HUD_COMPASS_OFFSET);
    if (offset == offset && fabsf(offset) < 100000.0f) /* a float, not garbage */
        now_entry()->offset = offset;
}

/* fci_aim.c, once a frame on foot: the view's yaw after this frame's turn (degrees, falling to the right) */
void fci_counter_view(float yaw)
{
    State *s = now_entry();
    s->yaw = yaw;
    s->known = 1;
}

/* for the renderer: the rounds (-1 unknown) and the heading (degrees clockwise from the HUD's north) for the
 * frame it draws, else the newest before it, else the newest; bit 0 of the result set when the heading is known */
int fci_counter_state(uint64_t frame, int *out_rounds, float *out_heading)
{
    for (int tries = 0; tries < 4; tries++) {
        const State *best = NULL;
        LONG64 f = -1;
        for (int i = 0; i < FRAMES; i++) {
            LONG64 g = ring[i].frame;
            if (g >= 0 && g <= (LONG64)frame && g > f) {
                f = g;
                best = &ring[i];
            }
        }
        if (!best && newest >= 0)
            best = &ring[newest % FRAMES];
        if (!best)
            break;
        LONG64 before = best->frame;
        int rounds = (int)best->rounds, known = best->known ? 1 : 0;
        /* the strip's middle shows the bearing -(yaw + 90 + offset): its value 0 is north (re/notes/WEAPONS.md,
         * checked against the HUD's letters with 02_Native's offset of -90) */
        float heading = fmodf(-(best->yaw + 90.0f + best->offset), 360.0f);
        MemoryBarrier();
        if (best->frame != before) /* reused while read */
            continue;
        *out_rounds = rounds;
        *out_heading = heading < 0 ? heading + 360.0f : heading;
        return known;
    }
    *out_rounds = -1;
    *out_heading = 0;
    return 0;
}
